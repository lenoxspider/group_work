"""
Project data transfer objects.

What it does:
- Encapsulates payloads for project dashboard and lifecycle archive operations.

What it does NOT do:
- Does NOT execute business logic or database queries.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List
from src.application.dtos.report_dtos import GuildStandingItemDTO

@dataclass(frozen=True)
class ProjectStatusDTO:
    """Dashboard view of current active project metrics."""
    guild_id: str
    status: str
    total_tasks: int
    completed_tasks: int
    pending_tasks: int
    active_deadlines_count: int
    nearest_deadline_name: Optional[str]
    nearest_deadline_due: Optional[datetime]
    total_files_submitted: int

@dataclass(frozen=True)
class ProjectArchiveSummaryDTO:
    """Final project retrospective report summary."""
    guild_id: str
    archived_at: datetime
    archived_by: str
    total_tasks_completed: int
    total_files_submitted: int
    standings: List[GuildStandingItemDTO]
