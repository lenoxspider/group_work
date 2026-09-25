"""
Extension request data transfer objects.

What it does:
- Encapsulates input and output payloads for extension request workflows.

What it does NOT do:
- Does NOT contain business validation or domain rules.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Set

@dataclass(frozen=True)
class CreateExtensionDTO:
    """Input payload to request a task extension."""
    task_id: str
    guild_id: str
    requester_id: str
    proposed_due_date: datetime
    reason: str

@dataclass(frozen=True)
class CastVoteDTO:
    """Input payload to cast a peer vote on an extension request."""
    request_id: str
    user_id: str
    approve: bool

@dataclass(frozen=True)
class ExtensionResultDTO:
    """Output payload representing extension request state."""
    request_id: str
    task_id: str
    guild_id: str
    requester_id: str
    proposed_due_date: datetime
    reason: str
    status: str
    approvals_count: int
    rejections_count: int
    approvals: Set[str]
    rejections: Set[str]
    created_at: datetime
    resolved_at: Optional[datetime] = None

    @property
    def is_resolved(self) -> bool:
        return self.status != "PENDING"

    @property
    def is_approved(self) -> bool:
        return self.status == "APPROVED"
