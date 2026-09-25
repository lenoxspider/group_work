"""
Extension request aggregate entity.

What it does:
- Models a peer-voted extension request for an assigned task.
- Tracks team approvals and rejections.
- Evaluates majority voting outcome to resolve the request.

What it does NOT do:
- Does NOT execute SQL or database queries.
- Does NOT dispatch Discord UI components.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Set, Optional
from src.domain.errors import ValidationError

@dataclass
class ExtensionRequest:
    """Represents a formal team-voted request to extend a task deadline."""
    request_id: str
    task_id: str
    guild_id: str
    requester_id: str
    proposed_due_date: datetime
    reason: str
    created_at: datetime
    status: str = "PENDING"  # PENDING, APPROVED, REJECTED
    approvals: Set[str] = field(default_factory=set)
    rejections: Set[str] = field(default_factory=set)
    resolved_at: Optional[datetime] = None

    def __post_init__(self):
        if not self.request_id.strip():
            raise ValidationError("Request ID cannot be empty.")
        if not self.task_id.strip():
            raise ValidationError("Task ID cannot be empty.")
        if not self.requester_id.strip():
            raise ValidationError("Requester ID cannot be empty.")
        if not self.reason.strip():
            raise ValidationError("Extension reason cannot be empty.")

    @property
    def is_resolved(self) -> bool:
        """Indicates whether voting has concluded."""
        return self.status != "PENDING"

    @property
    def total_votes(self) -> int:
        """Total distinct peer votes cast so far."""
        return len(self.approvals) + len(self.rejections)

    def cast_vote(self, user_id: str, approve: bool) -> None:
        """
        Casts or updates a peer vote on this extension request.

        Args:
            user_id: Discord user ID of the voter.
            approve: True for approve, False for reject.

        Raises:
            ValidationError: If user is the requester or vote is already resolved.
        """
        if self.is_resolved:
            raise ValidationError("Voting has already closed on this extension request.")
        if str(user_id) == str(self.requester_id):
            raise ValidationError("You cannot vote on your own extension request.")

        clean_user = str(user_id)
        if approve:
            self.approvals.add(clean_user)
            self.rejections.discard(clean_user)
        else:
            self.rejections.add(clean_user)
            self.approvals.discard(clean_user)

    def resolve_majority(self, timestamp: Optional[datetime] = None) -> bool:
        """
        Concludes the vote based on the majority of votes cast.

        Returns:
            bool: True if approved, False if rejected/tied.
        """
        if self.is_resolved:
            raise ValidationError("Extension request is already resolved.")
        if self.total_votes == 0:
            raise ValidationError("Cannot conclude vote: no votes have been cast yet.")

        self.resolved_at = timestamp or datetime.now(timezone.utc)
        if len(self.approvals) > len(self.rejections):
            self.status = "APPROVED"
            return True
        else:
            self.status = "REJECTED"
            return False
