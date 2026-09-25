"""
Task repository interface.

What it does:
- Defines the data access contract for Task aggregates.

What it does NOT do:
- Does NOT implement SQL queries or database connections.
"""

from datetime import datetime
from typing import Protocol, Optional, List
from src.domain.entities.task import Task

class TaskRepository(Protocol):
    """Abstract interface for task persistence."""

    async def save(self, task: Task) -> None:
        """Saves a new or existing task aggregate."""
        ...

    async def get_by_id(self, task_id: str) -> Optional[Task]:
        """Retrieves a task by its unique identifier."""
        ...

    async def get_pending_by_guild(self, guild_id: str) -> List[Task]:
        """Retrieves all incomplete tasks for a specific guild."""
        ...

    async def get_all_pending(self) -> List[Task]:
        """Retrieves all incomplete tasks across all guilds for reminder checks."""
        ...

    async def update_reminder(self, task_id: str, reminder_tier: str) -> None:
        """Updates reminder flags ('24h' or '1h') for a task."""
        ...

    async def update_progress(self, task_id: str, in_progress: bool) -> None:
        """Updates in-progress status flag for a task."""
        ...

    async def mark_shame_logged(self, task_id: str) -> None:
        """Marks a task as posted to Wall of Shame."""
        ...

    async def get_overdue_unshamed(self, now: Optional[datetime] = None) -> List[Task]:
        """Retrieves open overdue tasks that have not yet been shamed."""
        ...

    async def update_due_date(self, task_id: str, new_due_date: datetime) -> None:
        """Updates the due date and resets reminder and shame flags."""
        ...
