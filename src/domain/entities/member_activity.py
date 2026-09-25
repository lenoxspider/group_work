"""
Member activity aggregate entity.

What it does:
- Tracks individual student activity metrics (messages, files, completed tasks).
- Calculates objective contribution ratios and participation scores.

What it does NOT do:
- Does NOT listen to Discord events or gateway events.
- Does NOT execute database queries.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from src.domain.errors import ValidationError

# Weight constants for contribution score
TASK_WEIGHT: float = 3.0
FILE_WEIGHT: float = 2.0
MESSAGE_WEIGHT: float = 0.1

@dataclass
class MemberActivity:
    """Represents a member's accumulated group work activity."""
    guild_id: str
    user_id: str
    message_count: int = 0
    files_submitted: int = 0
    tasks_completed: int = 0
    last_active: Optional[datetime] = None

    def __post_init__(self):
        if not self.guild_id.strip():
            raise ValidationError("Guild ID cannot be empty.")
        if not self.user_id.strip():
            raise ValidationError("User ID cannot be empty.")

    def record_message(self, timestamp: Optional[datetime] = None) -> None:
        """Increments message count and updates last active timestamp."""
        self.message_count += 1
        self.last_active = timestamp or datetime.now(timezone.utc)

    def record_file_submission(self, timestamp: Optional[datetime] = None) -> None:
        """Increments file submission count and updates timestamp."""
        self.files_submitted += 1
        self.last_active = timestamp or datetime.now(timezone.utc)

    def record_task_completed(self, timestamp: Optional[datetime] = None) -> None:
        """Increments completed tasks count and updates timestamp."""
        self.tasks_completed += 1
        self.last_active = timestamp or datetime.now(timezone.utc)

    @property
    def contribution_score(self) -> float:
        """Computes a weighted composite score of team contribution."""
        return (
            (self.tasks_completed * TASK_WEIGHT) +
            (self.files_submitted * FILE_WEIGHT) +
            (self.message_count * MESSAGE_WEIGHT)
        )
