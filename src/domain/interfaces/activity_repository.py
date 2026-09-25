"""
Member activity repository interface.

What it does:
- Defines the data access contract for tracking member contributions.

What it does NOT do:
- Does NOT execute SQL statements.
"""

from typing import Protocol, Optional, List
from src.domain.entities.member_activity import MemberActivity

class ActivityRepository(Protocol):
    """Abstract interface for member activity persistence."""

    async def get_activity(self, guild_id: str, user_id: str) -> Optional[MemberActivity]:
        """Retrieves activity record for a specific member in a guild."""
        ...

    async def record_message(self, guild_id: str, user_id: str) -> None:
        """Atomically increments message count for member."""
        ...

    async def record_file_submission(self, guild_id: Optional[str], user_id: str) -> None:
        """Atomically increments file submission count for member."""
        ...

    async def record_task_completed(self, guild_id: str, user_id: str, is_on_time: bool = True) -> None:
        """Atomically increments completed tasks count, tracking streaks and on-time rates."""
        ...

    async def reset_streak(self, guild_id: str, user_id: str) -> None:
        """Resets member's current on-time streak to 0 upon overdue item."""
        ...

    async def get_guild_standings(self, guild_id: str) -> List[MemberActivity]:
        """Retrieves sorted activity ranking for all active members in a guild."""
        ...
