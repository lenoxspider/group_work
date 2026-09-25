"""
Channel binding repository interface.

What it does:
- Defines abstract contract for storing and querying persistent guild-channel bindings.

What it does NOT do:
- Does NOT execute SQL statements or import concrete database drivers.
"""

from typing import Protocol, Optional, Dict
from src.domain.entities.channel_binding import ChannelBinding

class ChannelBindingRepository(Protocol):
    """Abstract persistence interface for guild channel ID bindings."""

    async def save_binding(self, binding: ChannelBinding) -> None:
        """Persists or updates a guild channel binding."""
        ...

    async def get_binding(self, guild_id: str, channel_key: str) -> Optional[str]:
        """Retrieves the bound Discord channel snowflake ID for a key, or None if unbound."""
        ...

    async def list_bindings(self, guild_id: str) -> Dict[str, str]:
        """Retrieves all logical channel keys and their bound Discord channel IDs in a guild."""
        ...

    async def delete_binding(self, guild_id: str, channel_key: str) -> None:
        """Removes a binding when a channel is retired or deleted."""
        ...
