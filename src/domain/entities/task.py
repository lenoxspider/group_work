"""
Task aggregate entity.

What it does:
- Models a group task deliverable with assignment and due date.
- Manages completion state transitions.
- Evaluates eligibility for T-24h and T-1h reminders.

What it does NOT do:
- Does NOT execute database queries or SQL.
- Does NOT dispatch Discord notifications or API requests.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
from src.domain.errors import ValidationError, TaskAlreadyCompletedError

@dataclass
class Task:
    """Represents a discrete task assigned to a team member."""
    task_id: str
    guild_id: str
    channel_id: Optional[str]
    message_id: Optional[str]
    description: str
    assigned_to: str
    due_date: datetime
    created_at: datetime
    completed_at: Optional[datetime] = None
    reminded_24h: bool = False
    reminded_1h: bool = False

    def __post_init__(self):
        if not self.task_id.strip():
            raise ValidationError("Task ID cannot be empty.")
        if not self.description.strip():
            raise ValidationError("Task description cannot be empty.")
        if not self.assigned_to.strip():
            raise ValidationError("Assignee ID cannot be empty.")

    @property
    def is_completed(self) -> bool:
        """Indicates whether the task has been marked complete."""
        return self.completed_at is not None

    def mark_completed(self, completed_time: Optional[datetime] = None) -> None:
        """
        Transitions the task to completed state.

        Args:
            completed_time: Optional explicit timestamp of completion.

        Raises:
            TaskAlreadyCompletedError: If already completed.
        """
        if self.is_completed:
            raise TaskAlreadyCompletedError(f"Task {self.task_id} is already completed.")
        self.completed_at = completed_time or datetime.now(timezone.utc)

    def is_due_within(self, current_time: datetime, delta: timedelta) -> bool:
        """Checks if due date falls within the specified delta from current time."""
        time_left = self.due_date - current_time
        return timedelta(0) < time_left <= delta

    def needs_24h_reminder(self, current_time: datetime) -> bool:
        """Evaluates if T-24h reminder is due and unsent."""
        if self.is_completed or self.reminded_24h:
            return False
        return self.is_due_within(current_time, timedelta(hours=24))

    def needs_1h_reminder(self, current_time: datetime) -> bool:
        """Evaluates if T-1h reminder is due and unsent."""
        if self.is_completed or self.reminded_1h:
            return False
        return self.is_due_within(current_time, timedelta(hours=1))
