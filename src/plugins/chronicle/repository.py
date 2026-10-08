"""SQLite persistence for the national chronicle."""

from typing import Dict, List

from src.infrastructure.database.sqlite import connect

_COLS = ("id", "guild_id", "kind", "text", "created_at")


class SQLiteChronicleRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def add(self, guild_id: str, kind: str, text: str, created_at: str) -> None:
        async with connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO chronicle_entries (guild_id, kind, text, created_at, posted) "
                "VALUES (?, ?, ?, ?, 0)",
                (guild_id, kind, text, created_at),
            )
            await db.commit()

    async def list_unposted(self, limit: int = 25) -> List[dict]:
        async with connect(self.db_path) as db:
            async with db.execute(
                "SELECT id, guild_id, kind, text, created_at FROM chronicle_entries "
                "WHERE posted = 0 ORDER BY id LIMIT ?",
                (limit,),
            ) as cur:
                rows = await cur.fetchall()
        return [dict(zip(_COLS, row)) for row in rows]

    async def mark_posted(self, entry_id: int) -> None:
        async with connect(self.db_path) as db:
            await db.execute(
                "UPDATE chronicle_entries SET posted = 1 WHERE id = ?", (entry_id,)
            )
            await db.commit()

    async def recent(self, guild_id: str, limit: int = 10) -> List[dict]:
        async with connect(self.db_path) as db:
            async with db.execute(
                "SELECT kind, text, created_at FROM chronicle_entries "
                "WHERE guild_id = ? ORDER BY id DESC LIMIT ?",
                (guild_id, limit),
            ) as cur:
                rows = await cur.fetchall()
        # oldest-first for reading
        return [
            {"kind": r[0], "text": r[1], "created_at": r[2]} for r in reversed(rows)
        ]

    async def count_by_kind(self, guild_id: str) -> Dict[str, int]:
        async with connect(self.db_path) as db:
            async with db.execute(
                "SELECT kind, COUNT(*) FROM chronicle_entries WHERE guild_id = ? GROUP BY kind",
                (guild_id,),
            ) as cur:
                rows = await cur.fetchall()
        return {r[0]: r[1] for r in rows}
