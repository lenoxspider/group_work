"""
SQLite implementation of ActivityRepository.

What it does:
- Persists and queries student contribution activity records.
- Calculates and sorts activity standings across team members.

What it does NOT do:
- Does NOT parse raw messages or Discord events.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import aiosqlite

from src.domain.entities.member_activity import MemberActivity
from src.domain.interfaces.activity_repository import ActivityRepository

class SQLiteActivityRepository(ActivityRepository):
    """aiosqlite-backed repository for MemberActivity aggregates."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _row_to_entity(self, row: Dict[str, Any]) -> MemberActivity:
        last_active = datetime.fromisoformat(row["last_active"]) if row.get("last_active") else None
        return MemberActivity(
            guild_id=row["guild_id"],
            user_id=row["user_id"],
            message_count=row["message_count"],
            files_submitted=row["files_submitted"],
            tasks_completed=row["tasks_completed"],
            last_active=last_active
        )

    async def get_activity(self, guild_id: str, user_id: str) -> Optional[MemberActivity]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM member_activity WHERE guild_id = ? AND user_id = ?",
                (guild_id, user_id)
            ) as cursor:
                row = await cursor.fetchone()
                return self._row_to_entity(dict(row)) if row else None

    async def record_message(self, guild_id: str, user_id: str) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO member_activity (guild_id, user_id, message_count, last_active)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    message_count = message_count + 1,
                    last_active = excluded.last_active
            """, (guild_id, user_id, now_str))
            await db.commit()

    async def record_file_submission(self, guild_id: Optional[str], user_id: str) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            if guild_id:
                await db.execute("""
                    INSERT INTO member_activity (guild_id, user_id, files_submitted, last_active)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        files_submitted = files_submitted + 1,
                        last_active = excluded.last_active
                """, (guild_id, user_id, now_str))
            else:
                await db.execute("""
                    UPDATE member_activity
                    SET files_submitted = files_submitted + 1,
                        last_active = ?
                    WHERE user_id = ?
                """, (now_str, user_id))
            await db.commit()

    async def record_task_completed(self, guild_id: str, user_id: str) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO member_activity (guild_id, user_id, tasks_completed, last_active)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    tasks_completed = tasks_completed + 1,
                    last_active = excluded.last_active
            """, (guild_id, user_id, now_str))
            await db.commit()

    async def get_guild_standings(self, guild_id: str) -> List[MemberActivity]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM member_activity WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                entities = [self._row_to_entity(dict(r)) for r in rows]
                entities.sort(key=lambda e: e.contribution_score, reverse=True)
                return entities
