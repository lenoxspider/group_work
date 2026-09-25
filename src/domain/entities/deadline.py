"""
Deadline aggregate entity.

What it does:
- Models a major project milestone with strict due datetime.
- Calculates remaining duration and overdue state.
- Evaluates eligibility for T-72h, T-24h, and T-6h team alerts.

What it does NOT do:
- Does NOT execute SQL or persist state.
- Does NOT interact with Discord channels or send messages.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Tuple
from src.domain.errors import ValidationError, DeadlineAlreadyCompletedError

@dataclass
class Deadline:
    """Represents a project deadline with alert triggers."""
    deadline_id: str
    guild_id: str
    channel_id: str
    message_id: str
    name: str
    due_datetime: datetime
    created_at: datetime
    is_completed: bool = False
    reminded_72h: bool = False
    reminded_24h: bool = False
    reminded_6h: bool = False

    def __post_init__(self):
        if not self.deadline_id.strip():
            raise ValidationError("Deadline ID cannot be empty.")
        if not self.name.strip():
            raise ValidationError("Deadline name cannot be empty.")

    def mark_completed(self) -> None:
        """
        Marks deadline as completed.

        Raises:
            DeadlineAlreadyCompletedError: If already completed.
        """
        if self.is_completed:
            raise DeadlineAlreadyCompletedError(f"Deadline {self.deadline_id} is already completed.")
        self.is_completed = True

    def get_time_remaining(self, current_time: datetime) -> Tuple[int, int, int, bool]:
        """
        Calculates remaining days, hours, and minutes.

        Returns:
            Tuple[int, int, int, bool]: (days, hours, minutes, is_overdue)
        """
        diff = self.due_datetime - current_time
        if diff.total_seconds() <= 0:
            return 0, 0, 0, True
        total_seconds = int(diff.total_seconds())
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        return days, hours, minutes, False

    def needs_72h_alert(self, current_time: datetime) -> bool:
        """Evaluates if T-72h alert is due and unsent."""
        if self.is_completed or self.reminded_72h:
            return False
        time_left = self.due_datetime - current_time
        return timedelta(hours=24) < time_left <= timedelta(hours=72)

    def needs_24h_alert(self, current_time: datetime) -> bool:
        """Evaluates if T-24h alert is due and unsent."""
        if self.is_completed or self.reminded_24h:
            return False
        time_left = self.due_datetime - current_time
        return timedelta(hours=6) < time_left <= timedelta(hours=24)

    def needs_6h_alert(self, current_time: datetime) -> bool:
        """Evaluates if T-6h alert is due and unsent."""
        if self.is_completed or self.reminded_6h:
            return False
        time_left = self.due_datetime - current_time
        return timedelta(0) < time_left <= timedelta(hours=6)
