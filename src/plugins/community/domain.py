"""Community domain - membership status and the catizen/citizen split."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

CATIZEN = "catizen"
CITIZEN = "citizen"


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