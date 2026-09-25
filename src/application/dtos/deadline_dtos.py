"""
Deadline data transfer objects.

What it does:
- Encapsulates input and output payloads for milestone and deadline use cases.

What it does NOT do:
- Does NOT execute business logic or SQL.
"""

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class CreateDeadlineDTO:
    """Input payload to schedule a new project deadline."""
    guild_id: str
    channel_id: str
    message_id: str
    name: str
    due_datetime: datetime

@dataclass(frozen=True)
class DeadlineResultDTO:
    """Output payload representing deadline state."""
    deadline_id: str
    guild_id: str
    channel_id: str
    message_id: str
    name: str
    due_datetime: datetime
    created_at: datetime
    is_completed: bool

@dataclass(frozen=True)
class DeadlineAlertActionDTO:
    """Action payload indicating a deadline alert ping must be broadcast."""
    deadline_id: str
    guild_id: str
    channel_id: str
    name: str
    due_datetime: datetime
    alert_tier: str  # '72h', '24h', or '6h'
