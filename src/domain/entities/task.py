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
    reminded_6h: bool = False
    reminded_1h: bool = False
    is_in_progress: bool = False
    shame_logged: bool = False

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

    @property
    def is_on_time(self) -> Optional[bool]:
        """Returns True if completed on or before due date, False if late, None if open."""
        if not self.is_completed or not self.completed_at:
            return None
        return self.completed_at <= self.due_date

    def is_overdue(self, current_time: datetime) -> bool:
        """Indicates if the open task is past its deadline."""
        return not self.is_completed and current_time > self.due_date

    def set_in_progress(self, in_progress: bool = True) -> None:
        """Toggles the in-progress state of an open task."""
        if self.is_completed:
            raise TaskAlreadyCompletedError(f"Cannot change progress state on completed task {self.task_id}.")
        self.is_in_progress = in_progress

    def extend_due_date(self, new_due_date: datetime) -> None:
        """Extends task deadline and resets reminder thresholds."""
        if self.is_completed:
            raise TaskAlreadyCompletedError(f"Cannot extend completed task {self.task_id}.")
        if new_due_date <= self.due_date:
            raise ValidationError("Proposed extension date must be strictly after the current due date.")
        self.due_date = new_due_date
        self.reminded_24h = False
        self.reminded_6h = False
        self.reminded_1h = False
        self.shame_logged = False

    def mark_shame_logged(self) -> None:
        """Marks that this overdue task has been posted to Wall of Shame."""
        self.shame_logged = True

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
        self.is_in_progress = False

    def is_due_within(self, current_time: datetime, delta: timedelta) -> bool:
        """Checks if due date falls within the specified delta from current time."""
        time_left = self.due_date - current_time
        return timedelta(0) < time_left <= delta

    def needs_24h_reminder(self, current_time: datetime) -> bool:
        """Evaluates if T-24h reminder is due and unsent."""
        if self.is_completed or self.reminded_24h:
            return False
        return self.is_due_within(current_time, timedelta(hours=24))

    def needs_6h_reminder(self, current_time: datetime) -> bool:
        """Evaluates if T-6h escalation reminder is due and unsent."""
        if self.is_completed or self.reminded_6h:
            return False
        return self.is_due_within(current_time, timedelta(hours=6))

    def needs_1h_reminder(self, current_time: datetime) -> bool:
        """Evaluates if T-1h reminder is due and unsent."""
        if self.is_completed or self.reminded_1h:
            return False
        return self.is_due_within(current_time, timedelta(hours=1))
