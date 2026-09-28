"""SQLite persistence for pulse pacing state."""

from typing import Optional

import aiosqlite


class SQLitePulseRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def get_last_fired(self, guild_id: str) -> Optional[str]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT last_fired FROM pulse_state WHERE guild_id = ?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_last_fired(self, guild_id: str, ts: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO pulse_state (guild_id, last_fired) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET last_fired = excluded.last_fired",
                (guild_id, ts),
            )
            await db.commit()