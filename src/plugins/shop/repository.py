"""SQLite persistence for cosmetic purchases."""

from typing import List

import aiosqlite


class SQLiteShopRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def record(
        self, guild_id: str, user_id: str, item_id: str,
        price: int, role_id: str, bought_at: str,
    ) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO shop_purchases "
                "(guild_id, user_id, item_id, price, role_id, bought_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (guild_id, user_id, item_id, price, role_id, bought_at),
            )
            await db.commit()

    async def owns(self, guild_id: str, user_id: str, item_id: str) -> bool:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT 1 FROM shop_purchases WHERE guild_id = ? AND user_id = ? AND item_id = ?",
                (guild_id, user_id, item_id),
            ) as cur:
                return await cur.fetchone() is not None

    async def list_owned(self, guild_id: str, user_id: str) -> List[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT item_id FROM shop_purchases WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id),
            ) as cur:
                rows = await cur.fetchall()
                return [r[0] for r in rows]

    async def total_burned(self, guild_id: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COALESCE(SUM(price), 0) FROM shop_purchases WHERE guild_id = ?",
                (guild_id,),
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0
