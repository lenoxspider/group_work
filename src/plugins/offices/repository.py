"""SQLite persistence for the offices of state."""

from typing import List, Optional

from src.infrastructure.database.sqlite import connect


class SQLiteOfficesRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def set_holder(self, guild_id, office, user_id, appointed_at, appointed_by) -> None:
        async with connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO offices (guild_id, office, user_id, appointed_at, appointed_by) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(guild_id, office) DO UPDATE SET "
                "user_id = excluded.user_id, appointed_at = excluded.appointed_at, "
                "appointed_by = excluded.appointed_by",
                (guild_id, office, user_id, appointed_at, appointed_by),
            )
            await db.commit()

    async def clear_office(self, guild_id, office) -> None:
        async with connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM offices WHERE guild_id = ? AND office = ?", (guild_id, office)
            )
            await db.commit()

    async def holder(self, guild_id, office) -> Optional[str]:
        async with connect(self.db_path) as db:
            async with db.execute(
                "SELECT user_id FROM offices WHERE guild_id = ? AND office = ?", (guild_id, office)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def offices_held_by(self, guild_id, user_id) -> List[str]:
        async with connect(self.db_path) as db:
            async with db.execute(
                "SELECT office FROM offices WHERE guild_id = ? AND user_id = ?", (guild_id, user_id)
            ) as cur:
                return [r[0] for r in await cur.fetchall()]

    async def all_offices(self, guild_id) -> List[dict]:
        async with connect(self.db_path) as db:
            async with db.execute(
                "SELECT office, user_id, appointed_at FROM offices WHERE guild_id = ? ORDER BY office",
                (guild_id,),
            ) as cur:
                return [
                    {"office": r[0], "user_id": r[1], "appointed_at": r[2]}
                    for r in await cur.fetchall()
                ]
