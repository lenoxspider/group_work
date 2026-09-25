"""
Contribution report data transfer objects.

What it does:
- Encapsulates summary and detailed accountability metrics for members and teams.

What it does NOT do:
- Does NOT build Discord embeds or terminal output.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List

@dataclass(frozen=True)
class MemberReportDTO:
    """Individual member contribution metrics."""
    guild_id: str
    user_id: str
    message_count: int
    files_submitted: int
    tasks_completed: int
    pending_tasks: int
    completion_rate: int
    contribution_score: float
    last_active: Optional[datetime]

@dataclass(frozen=True)
class GuildStandingItemDTO:
    """Single line item in team contribution leaderboard."""
    user_id: str
    message_count: int
    files_submitted: int
    tasks_completed: int
    contribution_score: float

@dataclass(frozen=True)
class GuildReportDTO:
    """Full guild team standings overview."""
    guild_id: str
    standings: List[GuildStandingItemDTO]
