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
    on_time_tasks: int = 0
    current_streak: int = 0
    best_streak: int = 0
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

    def record_task_completed(self, is_on_time: bool = True, timestamp: Optional[datetime] = None) -> None:
        """
        Increments completed tasks, tracking on-time rates and streaks.

        Args:
            is_on_time: True if delivered before or on deadline, False if late.
            timestamp: Optional execution timestamp.
        """
        self.tasks_completed += 1
        if is_on_time:
            self.on_time_tasks += 1
            self.current_streak += 1
            self.best_streak = max(self.best_streak, self.current_streak)
        else:
            self.current_streak = 0
        self.last_active = timestamp or datetime.now(timezone.utc)

    def break_streak(self) -> None:
        """Resets the current on-time streak to 0 upon overdue violation."""
        self.current_streak = 0

    @property
    def on_time_rate(self) -> int:
        """Computes percentage of completed tasks that were delivered on time."""
        if self.tasks_completed == 0:
            return 100
        return int((self.on_time_tasks / self.tasks_completed) * 100)

    @property
    def rank_title(self) -> str:
        """Maps composite contribution score to gamified rank titles."""
        score = self.contribution_score
        if score < 10.0:
            return "Comrade 🎖️"
        elif score < 25.0:
            return "Sergeant 🎗️"
        elif score < 50.0:
            return "Colonel ⚔️"
        elif score < 100.0:
            return "Marshal 🌟"
        return "General Secretary 👑"

    @property
    def contribution_score(self) -> float:
        """Computes a weighted composite score of team contribution."""
        return (
            (self.tasks_completed * TASK_WEIGHT) +
            (self.files_submitted * FILE_WEIGHT) +
            (self.message_count * MESSAGE_WEIGHT)
        )
