"""Community domain - membership (catizen/citizen) and the tribunal's cases."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

CATIZEN = "catizen"
CITIZEN = "citizen"

# Case verdict / lifecycle
CASE_OPEN = "OPEN"
CASE_CONVICTED = "CONVICTED"
CASE_ACQUITTED = "ACQUITTED"
CASE_LAPSED = "LAPSED"

# Tribunal defaults
COURT_QUORUM = 3
COURT_VOTE_WINDOW_HOURS = 24
COURT_APPEAL_WINDOW_HOURS = 12
COURT_FALSE_WITNESS_FINE = 25

# Onboarding
CITIZEN_STIPEND_SPI = 100      # paid once on signing, so a new citizen can actually play


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Member:
    """A member's registration status in the guild's community."""
    guild_id: str
    user_id: str
    status: str = CATIZEN
    intro_task_id: Optional[str] = None
    intro_done: bool = False
    joined_at: str = ""
    signed_at: Optional[str] = None


@dataclass
class Case:
    """A tribunal case: a citizen's charge against another, judged by the jury."""
    case_id: str
    guild_id: str
    accuser_id: str
    accused_id: str
    law_id: str
    evidence: str = ""
    defense: str = ""
    status: str = CASE_OPEN
    guilty_votes: str = ""
    innocent_votes: str = ""
    round: int = 1
    message_id: str = ""
    channel_id: str = ""
    sentenced: bool = False
    created_at: str = ""
    opened_at: str = ""
    resolved_at: Optional[str] = None

    def guilty(self) -> list:
        return [u for u in self.guilty_votes.split(",") if u]

    def innocent(self) -> list:
        return [u for u in self.innocent_votes.split(",") if u]
