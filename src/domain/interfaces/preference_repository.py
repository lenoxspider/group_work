"""
Member preference repository interface.

What it does:
- Defines the data access contract for MemberPreference aggregates.

What it does NOT do:
- Does NOT execute SQL statements or database queries.
"""

from typing import Protocol, Optional
from src.domain.entities.member_preference import MemberPreference

class PreferenceRepository(Protocol):
    """Abstract interface for student notification and timezone preferences."""

    async def save(self, preference: MemberPreference) -> None:
        """Persists a new or updated member preference."""
        ...

    async def get_preference(self, guild_id: str, user_id: str) -> Optional[MemberPreference]:
        """Retrieves stored preference for a member in a guild."""
        ...
