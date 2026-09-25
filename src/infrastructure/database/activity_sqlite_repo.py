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
            message_count=row.get("message_count", 0),
            files_submitted=row.get("files_submitted", 0),
            tasks_completed=row.get("tasks_completed", 0),
            on_time_tasks=row.get("on_time_tasks", 0),
            current_streak=row.get("current_streak", 0),
            best_streak=row.get("best_streak", 0),
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

    async def record_task_completed(self, guild_id: str, user_id: str, is_on_time: bool = True) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        on_time_flag = 1 if is_on_time else 0
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO member_activity (
                    guild_id, user_id, tasks_completed, on_time_tasks,
                    current_streak, best_streak, last_active
                )
                VALUES (?, ?, 1, ?, ?, ?, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    tasks_completed = tasks_completed + 1,
                    on_time_tasks = on_time_tasks + (CASE WHEN ? = 1 THEN 1 ELSE 0 END),
                    current_streak = (CASE WHEN ? = 1 THEN current_streak + 1 ELSE 0 END),
                    best_streak = (CASE 
                        WHEN ? = 1 AND (current_streak + 1 > best_streak) THEN current_streak + 1 
                        ELSE best_streak 
                    END),
                    last_active = excluded.last_active
            """, (
                guild_id, user_id, on_time_flag, on_time_flag, on_time_flag, now_str,
                on_time_flag, on_time_flag, on_time_flag
            ))
            await db.commit()

    async def reset_streak(self, guild_id: str, user_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE member_activity
                SET current_streak = 0
                WHERE guild_id = ? AND user_id = ?
            """, (guild_id, user_id))
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
