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
        verified = datetime.fromisoformat(row["verified_at"]) if row.get("verified_at") else None
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
            reminded_6h=bool(row.get("reminded_6h", 0)),
            reminded_1h=bool(row["reminded_1h"]),
            is_in_progress=bool(row.get("is_in_progress", 0)),
            shame_logged=bool(row.get("shame_logged", 0)),
            verifier_id=row.get("verifier_id"),
            verified_at=verified,
            verified_by=row.get("verified_by")
        )

    async def save(self, task: Task) -> None:
        completed_str = task.completed_at.isoformat() if task.completed_at else None
        verified_str = task.verified_at.isoformat() if task.verified_at else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO tasks (
                    task_id, guild_id, channel_id, message_id, description,
                    assigned_to, due_date, created_at, completed_at,
                    reminded_24h, reminded_6h, reminded_1h, is_in_progress, shame_logged,
                    verifier_id, verified_at, verified_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(task_id) DO UPDATE SET
                    channel_id = excluded.channel_id,
                    message_id = excluded.message_id,
                    description = excluded.description,
                    assigned_to = excluded.assigned_to,
                    due_date = excluded.due_date,
                    completed_at = excluded.completed_at,
                    reminded_24h = excluded.reminded_24h,
                    reminded_6h = excluded.reminded_6h,
                    reminded_1h = excluded.reminded_1h,
                    is_in_progress = excluded.is_in_progress,
                    shame_logged = excluded.shame_logged,
                    verifier_id = excluded.verifier_id,
                    verified_at = excluded.verified_at,
                    verified_by = excluded.verified_by
            """, (
                task.task_id, task.guild_id, task.channel_id, task.message_id,
                task.description, task.assigned_to, task.due_date.isoformat(),
                task.created_at.isoformat(), completed_str,
                1 if task.reminded_24h else 0, 1 if task.reminded_6h else 0,
                1 if task.reminded_1h else 0, 1 if task.is_in_progress else 0,
                1 if task.shame_logged else 0,
                task.verifier_id, verified_str, task.verified_by
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
        if reminder_tier == "24h":
            col = "reminded_24h"
        elif reminder_tier == "6h":
            col = "reminded_6h"
        else:
            col = "reminded_1h"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(f"UPDATE tasks SET {col} = 1 WHERE task_id = ?", (task_id,))
            await db.commit()

    async def update_progress(self, task_id: str, in_progress: bool) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE tasks SET is_in_progress = ? WHERE task_id = ?", (1 if in_progress else 0, task_id))
            await db.commit()

    async def mark_shame_logged(self, task_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE tasks SET shame_logged = 1 WHERE task_id = ?", (task_id,))
            await db.commit()

    async def update_due_date(self, task_id: str, new_due_date: datetime) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                UPDATE tasks
                SET due_date = ?, reminded_24h = 0, reminded_6h = 0, reminded_1h = 0, shame_logged = 0
                WHERE task_id = ?
            """, (new_due_date.isoformat(), task_id))
            await db.commit()

    async def get_overdue_unshamed(self, now: Optional[datetime] = None) -> List[Task]:
        now_dt = now or datetime.now(timezone.utc)
        now_str = now_dt.isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM tasks WHERE completed_at IS NULL AND shame_logged = 0 AND due_date < ?",
                (now_str,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_entity(dict(r)) for r in rows]
