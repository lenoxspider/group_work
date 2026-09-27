"""SQLite implementation of the bank repository.

All mutations run inside a single BEGIN IMMEDIATE transaction so
concurrent transfers cannot double-spend. Balances always change
atomically with their ledger row.
"""

import uuid

import aiosqlite

from src.plugins.bank.domain import (
    InsufficientFunds,
    InvalidAmount,
    SelfTransfer,
    TREASURY,
    Transaction,
    utcnow,
)


class SQLiteBankRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def get_balance(self, guild_id: str, user_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT balance FROM bank_accounts WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            )
            row = await cur.fetchone()
            return row[0] if row else 0

    async def ensure_account(self, guild_id: str, user_id: str) -> None:
        await self._open_account(guild_id, user_id)

    async def _open_account(self, guild_id: str, user_id: str) -> None:
        now = utcnow()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO bank_accounts (guild_id, user_id, balance, created_at, updated_at) "
                "VALUES (?, ?, 0, ?, ?)",
                (guild_id, user_id, now, now),
            )
            await db.commit()

    async def transfer(
        self,
        guild_id: str,
        from_user: str,
        to_user: str,
        amount: int,
        reason: str = "",
    ) -> Transaction:
        if amount < 0:
            raise InvalidAmount("amount cannot be negative")
        if amount == 0:
            return Transaction(uuid.uuid4().hex, guild_id, from_user, to_user, 0, reason, utcnow())
        if from_user == to_user:
            raise SelfTransfer("cannot transfer to yourself")

        now = utcnow()
        tx_id = uuid.uuid4().hex

        db = await aiosqlite.connect(self.db_path)
        try:
            await db.execute("BEGIN IMMEDIATE")

            await db.execute(
                "INSERT OR IGNORE INTO bank_accounts (guild_id, user_id, balance, created_at, updated_at) "
                "VALUES (?, ?, 0, ?, ?)",
                (guild_id, from_user, now, now),
            )
            await db.execute(
                "INSERT OR IGNORE INTO bank_accounts (guild_id, user_id, balance, created_at, updated_at) "
                "VALUES (?, ?, 0, ?, ?)",
                (guild_id, to_user, now, now),
            )

            if from_user != TREASURY:
                cur = await db.execute(
                    "SELECT balance FROM bank_accounts WHERE guild_id = ? AND user_id = ?",
                    (guild_id, from_user),
                )
                row = await cur.fetchone()
                balance = row[0] if row else 0
                if amount > balance:
                    raise InsufficientFunds(
                        f"{from_user} holds {balance} spi, attempted {amount}"
                    )

            await db.execute(
                "UPDATE bank_accounts SET balance = balance - ?, updated_at = ? "
                "WHERE guild_id = ? AND user_id = ?",
                (amount, now, guild_id, from_user),
            )
            await db.execute(
                "UPDATE bank_accounts SET balance = balance + ?, updated_at = ? "
                "WHERE guild_id = ? AND user_id = ?",
                (amount, now, guild_id, to_user),
            )
            await db.execute(
                "INSERT INTO bank_transactions "
                "(tx_id, guild_id, from_user, to_user, amount, reason, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (tx_id, guild_id, from_user, to_user, amount, reason, now),
            )

            await db.commit()
        except Exception:
            await db.rollback()
            raise
        finally:
            await db.close()

        return Transaction(tx_id, guild_id, from_user, to_user, amount, reason, now)

    async def ledger(self, guild_id: str, user_id: str, limit: int = 20) -> list[Transaction]:
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                "SELECT tx_id, guild_id, from_user, to_user, amount, reason, created_at "
                "FROM bank_transactions "
                "WHERE guild_id = ? AND (from_user = ? OR to_user = ?) "
                "ORDER BY created_at DESC LIMIT ?",
                (guild_id, user_id, user_id, limit),
            )
            rows = await cur.fetchall()
            return [Transaction(*r) for r in rows]