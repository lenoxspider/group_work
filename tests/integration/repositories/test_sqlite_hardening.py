"""Tests for the SQLite concurrency hardening.

The substantive change is WAL. The default journal mode is "delete", under which
a writer blocks readers; this bot has seven background loops plus user commands
sharing one file, so that contention is routine rather than exotic.

Connections already waited 5s for a lock before this change - aiosqlite inherits
sqlite3.connect(timeout=5.0) - so the busy timeout asserted here documents an
explicit, centrally tunable value rather than a fix.

Also covers migrations staying idempotent across restarts without swallowing
genuine failures.
"""

import asyncio
import os
import tempfile
import unittest

import aiosqlite

from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.database.sqlite import BUSY_TIMEOUT_MS, connect, open_connection
from src.plugins.bank.domain import TREASURY
from src.plugins.bank.repository import SQLiteBankRepository
from src.plugins.bank.schema import BANK_SCHEMA

GUILD = "guild-hardening"


class TestSqliteHardening(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)

    async def asyncTearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    async def _pragma(self, name: str):
        async with connect(self.db_path) as db:
            rows = await db.execute_fetchall(f"PRAGMA {name}")
            return rows[0][0]

    async def _bank_manager(self) -> DatabaseManager:
        mgr = DatabaseManager(self.db_path)
        mgr.register_plugin_schema("bank", BANK_SCHEMA)
        return mgr

    async def test_helper_connections_carry_an_explicit_busy_timeout(self):
        self.assertEqual(await self._pragma("busy_timeout"), BUSY_TIMEOUT_MS)

    async def test_open_connection_applies_it_too(self):
        db = await open_connection(self.db_path)
        try:
            rows = await db.execute_fetchall("PRAGMA busy_timeout")
            self.assertEqual(rows[0][0], BUSY_TIMEOUT_MS)
        finally:
            await db.close()

    async def test_fresh_databases_default_to_the_rollback_journal(self):
        """Establishes the baseline WAL is replacing."""
        async with aiosqlite.connect(self.db_path) as db:
            rows = await db.execute_fetchall("PRAGMA journal_mode")
        self.assertEqual(rows[0][0].lower(), "delete")

    async def test_initialize_schema_enables_wal(self):
        await DatabaseManager(self.db_path).initialize_schema()
        async with aiosqlite.connect(self.db_path) as db:
            rows = await db.execute_fetchall("PRAGMA journal_mode")
        self.assertEqual(rows[0][0].lower(), "wal")

    async def test_wal_is_persisted_for_every_later_connection(self):
        await DatabaseManager(self.db_path).initialize_schema()
        self.assertEqual(str(await self._pragma("journal_mode")).lower(), "wal")

    async def test_migrations_are_idempotent_across_restarts(self):
        mgr = DatabaseManager(self.db_path)
        mgr.register_plugin_schema(
            "probe", ["CREATE TABLE IF NOT EXISTS probe (id TEXT PRIMARY KEY, a TEXT)"]
        )
        mgr.register_plugin_migrations("probe", [("probe", "b", "TEXT")])
        await mgr.initialize_schema()
        await mgr.initialize_schema()  # second boot must not raise
        async with connect(self.db_path) as db:
            cols = [r[1] for r in await db.execute_fetchall("PRAGMA table_info(probe)")]
        self.assertIn("b", cols)

    async def test_concurrent_transfers_all_land(self):
        """The path that matters most: money moving from several loops at once."""
        mgr = await self._bank_manager()
        await mgr.initialize_schema()
        repo = SQLiteBankRepository(self.db_path)

        async def grant(i: int):
            await repo.transfer(GUILD, TREASURY, f"user{i}", 10, "concurrency probe")

        results = await asyncio.gather(*[grant(i) for i in range(30)], return_exceptions=True)
        failures = [r for r in results if isinstance(r, Exception)]
        self.assertEqual(failures, [], f"concurrent transfers raised: {failures[:3]}")

        for i in range(30):
            self.assertEqual(await repo.get_balance(GUILD, f"user{i}"), 10)

    async def test_writes_complete_while_readers_hammer(self):
        mgr = await self._bank_manager()
        await mgr.initialize_schema()
        repo = SQLiteBankRepository(self.db_path)
        await repo.ensure_account(GUILD, "reader")

        stop = asyncio.Event()

        async def hammer_reads():
            while not stop.is_set():
                await repo.get_balance(GUILD, "reader")

        readers = [asyncio.create_task(hammer_reads()) for _ in range(5)]
        try:
            await asyncio.wait_for(
                repo.transfer(GUILD, TREASURY, "reader", 50, "write under read load"),
                timeout=10,
            )
        finally:
            stop.set()
            await asyncio.gather(*readers, return_exceptions=True)

        self.assertEqual(await repo.get_balance(GUILD, "reader"), 50)


if __name__ == "__main__":
    unittest.main()
