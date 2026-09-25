"""
Project repository interface.

What it does:
- Defines the data access contract for ProjectState aggregates.

What it does NOT do:
- Does NOT execute SQL or touch SQLite directly.
"""

from typing import Protocol, Optional
from src.domain.entities.project_state import ProjectState

class ProjectRepository(Protocol):
    """Abstract interface for project state persistence."""

    async def get_state(self, guild_id: str) -> Optional[ProjectState]:
        """Retrieves project state for a guild."""
        ...

    async def save_state(self, state: ProjectState) -> None:
        """Saves or updates project state for a guild."""
        ...
