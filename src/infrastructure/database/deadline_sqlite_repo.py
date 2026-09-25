"""
SQLite implementation of DeadlineRepository.

What it does:
- Maps Deadline domain entity to and from SQLite rows.
- Executes async SQL queries using aiosqlite.

What it does NOT do:
- Does NOT contain business rules or validation.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import aiosqlite

from src.domain.entities.deadline import Deadline
from src.domain.interfaces.deadline_repository import DeadlineRepository

class SQLiteDeadlineRepository(DeadlineRepository):
    """aiosqlite-backed repository for Deadline aggregates."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _row_to_entity(self, row: Dict[str, Any]) -> Deadline:
        return Deadline(
            deadline_id=row["deadline_id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            name=row["name"],
            due_datetime=datetime.fromisoformat(row["due_datetime"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            is_completed=bool(row["is_completed"]),
            reminded_72h=bool(row["reminded_72h"]),
            reminded_24h=bool(row["reminded_24h"]),
            reminded_6h=bool(row["reminded_6h"])
        )

    async def save(self, deadline: Deadline) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO deadlines (
                    deadline_id, guild_id, channel_id, message_id, name,
                    due_datetime, created_at, is_completed,
                    reminded_72h, reminded_24h, reminded_6h
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(deadline_id) DO UPDATE SET
                    message_id = excluded.message_id,
                    name = excluded.name,
                    due_datetime = excluded.due_datetime,
                    is_completed = excluded.is_completed,
                    reminded_72h = excluded.reminded_72h,
                    reminded_24h = excluded.reminded_24h,
                    reminded_6h = excluded.reminded_6h
            """, (
                deadline.deadline_id, deadline.guild_id, deadline.channel_id,
                deadline.message_id, deadline.name, deadline.due_datetime.isoformat(),
                deadline.created_at.isoformat(), 1 if deadline.is_completed else 0,
                1 if deadline.reminded_72h else 0, 1 if deadline.reminded_24h else 0,
                1 if deadline.reminded_6h else 0
            ))
            await db.commit()

    async def get_by_id(self, deadline_id: str) -> Optional[Deadline]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM deadlines WHERE deadline_id = ?", (deadline_id,)) as cursor:
                row = await cursor.fetchone()
                return self._row_to_entity(dict(row)) if row else None

    async def get_active_by_guild(self, guild_id: str) -> List[Deadline]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM deadlines WHERE guild_id = ? AND is_completed = 0 ORDER BY due_datetime ASC",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_entity(dict(r)) for r in rows]

    async def get_all_active(self) -> List[Deadline]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM deadlines WHERE is_completed = 0 ORDER BY due_datetime ASC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_entity(dict(r)) for r in rows]

    async def update_reminder(self, deadline_id: str, alert_tier: str) -> None:
        col = f"reminded_{alert_tier}"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE deadlines SET {col} = 1 WHERE deadline_id = ?", (deadline_id,))
            await db.commit()
