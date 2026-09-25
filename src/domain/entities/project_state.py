"""
Project lifecycle aggregate entity.

What it does:
- Models the state of a group project (ACTIVE, ARCHIVED).
- Enforces state transition rules.

What it does NOT do:
- Does NOT interact with Discord APIs or execute database queries.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from src.domain.errors import ValidationError, AppError

class ProjectStatus(str, Enum):
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"

class ProjectAlreadyArchivedError(AppError):
    """Raised when attempting to archive an already archived project."""
    pass

@dataclass
class ProjectState:
    """Represents a guild project workspace status."""
    guild_id: str
    status: ProjectStatus = ProjectStatus.ACTIVE
    archived_at: Optional[datetime] = None
    archived_by: Optional[str] = None

    def __post_init__(self):
        if not self.guild_id.strip():
            raise ValidationError("Guild ID cannot be empty.")

    @property
    def is_archived(self) -> bool:
        return self.status == ProjectStatus.ARCHIVED

    def archive(self, archived_by_user_id: str, timestamp: Optional[datetime] = None) -> None:
        """Transitions project to archived state."""
        if self.is_archived:
            raise ProjectAlreadyArchivedError(f"Project for guild {self.guild_id} is already archived.")
        self.status = ProjectStatus.ARCHIVED
        self.archived_at = timestamp or datetime.now(timezone.utc)
        self.archived_by = archived_by_user_id
