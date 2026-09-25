"""
SQLite implementation of TaskRepository.

What it does:
- Maps Task domain entity to and from SQLite rows.
- Executes async SQL queries using aiosqlite.

What it does NOT do:
- Does NOT contain business rules or validation.
"""

from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
import aiosqlite

from src.domain.entities.task import Task
from src.domain.interfaces.task_repository import TaskRepository

class SQLiteTaskRepository(TaskRepository):
    """aiosqlite-backed repository for Task aggregates."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _row_to_entity(self, row: Dict[str, Any]) -> Task:
        completed = datetime.fromisoformat(row["completed_at"]) if row["completed_at"] else None
        return Task(
            task_id=row["task_id"],
            guild_id=row["guild_id"],
            channel_id=row["channel_id"],
            message_id=row["message_id"],
            description=row["description"],
            assigned_to=row["assigned_to"],
            due_date=datetime.fromisoformat(row["due_date"]),
            created_at=datetime.fromisoformat(row["created_at"]),
            completed_at=completed,
            reminded_24h=bool(row["reminded_24h"]),
            reminded_1h=bool(row["reminded_1h"])
        )

    async def save(self, task: Task) -> None:
        completed_str = task.completed_at.isoformat() if task.completed_at else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO tasks (
                    task_id, guild_id, channel_id, message_id, description,
                    assigned_to, due_date, created_at, completed_at,
                    reminded_24h, reminded_1h
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id,
                    description = excluded.description,
                    assigned_to = excluded.assigned_to,
                    due_date = excluded.due_date,
                    completed_at = excluded.completed_at,
                    reminded_24h = excluded.reminded_24h,
                    reminded_1h = excluded.reminded_1h
            """, (
                task.task_id, task.guild_id, task.channel_id, task.message_id,
                task.description, task.assigned_to, task.due_date.isoformat(),
                task.created_at.isoformat(), completed_str,
                1 if task.reminded_24h else 0, 1 if task.reminded_1h else 0
            ))
            await db.commit()

    async def get_by_id(self, task_id: str) -> Optional[Task]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()
                return self._row_to_entity(dict(row)) if row else None

    async def get_pending_by_guild(self, guild_id: str) -> List[Task]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tasks WHERE guild_id = ? AND completed_at IS NULL ORDER BY due_date ASC",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_entity(dict(r)) for r in rows]

    async def get_all_pending(self) -> List[Task]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tasks WHERE completed_at IS NULL ORDER BY due_date ASC"
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_entity(dict(r)) for r in rows]

    async def update_reminder(self, task_id: str, reminder_tier: str) -> None:
        col = "reminded_24h" if reminder_tier == "24h" else "reminded_1h"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE tasks SET {col} = 1 WHERE task_id = ?", (task_id,))
            await db.commit()
