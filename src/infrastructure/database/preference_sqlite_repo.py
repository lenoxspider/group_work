"""
SQLite implementation of PreferenceRepository.

What it does:
- Maps MemberPreference domain entity to and from SQLite rows.
- Executes async SQL queries using aiosqlite.

What it does NOT do:
- Does NOT contain business rules or validation.
"""

from datetime import datetime
from typing import Optional, Dict, Any
import aiosqlite

from src.domain.entities.member_preference import MemberPreference
from src.domain.interfaces.preference_repository import PreferenceRepository

class SQLitePreferenceRepository(PreferenceRepository):
    """aiosqlite-backed repository for MemberPreference aggregates."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _row_to_entity(self, row: Dict[str, Any]) -> MemberPreference:
        return MemberPreference(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            timezone_name=row["timezone_name"],
            quiet_hours_start=int(row["quiet_hours_start"]),
            quiet_hours_end=int(row["quiet_hours_end"]),
            updated_at=datetime.fromisoformat(row["updated_at"])
        )

    async def save(self, preference: MemberPreference) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO member_preferences (
                    guild_id, user_id, timezone_name, quiet_hours_start, quiet_hours_end, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    timezone_name = excluded.timezone_name,
                    quiet_hours_start = excluded.quiet_hours_start,
                    quiet_hours_end = excluded.quiet_hours_end,
                    updated_at = excluded.updated_at
            """, (
                preference.guild_id,
                preference.user_id,
                preference.timezone_name,
                preference.quiet_hours_start,
                preference.quiet_hours_end,
                preference.updated_at.isoformat()
            ))
            await db.commit()

    async def get_preference(self, guild_id: str, user_id: str) -> Optional[MemberPreference]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM member_preferences WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()
                return self._row_to_entity(dict(row)) if row else None
