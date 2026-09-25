"""
Task data transfer objects.

What it does:
- Encapsulates input and output payloads for task use cases.

What it does NOT do:
- Does NOT contain business rules or validation logic.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass(frozen=True)
class CreateTaskDTO:
    """Input payload to create a new task."""
    guild_id: str
    description: str
    assigned_to: str
    due_date: datetime
    channel_id: Optional[str] = None
    message_id: Optional[str] = None

@dataclass(frozen=True)
class TaskResultDTO:
    """Output payload representing task state."""
    task_id: str
    guild_id: str
    channel_id: Optional[str]
    message_id: Optional[str]
    description: str
    assigned_to: str
    due_date: datetime
    created_at: datetime
    completed_at: Optional[datetime]
    is_completed: bool

@dataclass(frozen=True)
class TaskReminderActionDTO:
    """Action payload indicating a reminder needs to be sent."""
    task_id: str
    guild_id: str
    user_id: str
    description: str
    due_date: datetime
    reminder_tier: str  # '24h' or '1h'
