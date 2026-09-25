"""
Extension request repository interface.

What it does:
- Defines the data access contract for ExtensionRequest aggregates.

What it does NOT do:
- Does NOT execute SQL statements or database queries.
"""

from typing import Protocol, Optional, List
from src.domain.entities.extension_request import ExtensionRequest

class ExtensionRepository(Protocol):
    """Abstract interface for extension request persistence."""

    async def save(self, extension: ExtensionRequest) -> None:
        """Persists a new or updated extension request."""
        ...

    async def get_by_id(self, request_id: str) -> Optional[ExtensionRequest]:
        """Retrieves an extension request by its unique identifier."""
        ...

    async def get_pending_by_task(self, task_id: str) -> Optional[ExtensionRequest]:
        """Retrieves an active PENDING extension request for a specific task if one exists."""
        ...

    async def get_pending_by_guild(self, guild_id: str) -> List[ExtensionRequest]:
        """Retrieves all PENDING extension requests for a guild."""
        ...
