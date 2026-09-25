"""
Deadline repository interface.

What it does:
- Defines the data access contract for Milestone/Deadline aggregates.

What it does NOT do:
- Does NOT execute database queries or SQL.
"""

from typing import Protocol, Optional, List
from src.domain.entities.deadline import Deadline

class DeadlineRepository(Protocol):
    """Abstract interface for deadline persistence."""

    async def save(self, deadline: Deadline) -> None:
        """Saves a new or updated deadline."""
        ...

    async def get_by_id(self, deadline_id: str) -> Optional[Deadline]:
        """Retrieves a deadline by its unique identifier."""
        ...

    async def get_active_by_guild(self, guild_id: str) -> List[Deadline]:
        """Retrieves all active deadlines for a given guild."""
        ...

    async def get_all_active(self) -> List[Deadline]:
        """Retrieves all active deadlines across all guilds for periodic alerts."""
        ...

    async def update_reminder(self, deadline_id: str, alert_tier: str) -> None:
        """Updates alert flags ('72h', '24h', or '6h') for a deadline."""
        ...
