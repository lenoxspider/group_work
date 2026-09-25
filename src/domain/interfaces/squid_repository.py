"""
Squid Game persistence repository interface.

What it does:
- Defines abstract contract for storing and querying Squid Game players and seasons.

What it does NOT do:
- Does NOT implement SQL queries or specific database drivers.
"""

from typing import Protocol, Optional, List
from src.domain.entities.squid_player import SquidPlayer
from src.domain.entities.squid_season import SquidSeason
from src.domain.entities.movement_anomaly import MovementAnomaly

class SquidRepository(Protocol):
    """Abstract persistence interface for Squid Game data."""

    async def save_player(self, player: SquidPlayer) -> None:
        """Persists or updates a player record."""
        ...

    async def get_player(self, guild_id: str, user_id: str) -> Optional[SquidPlayer]:
        """Retrieves a player by guild ID and Discord user ID."""
        ...

    async def get_player_by_number(self, guild_id: str, player_number: str) -> Optional[SquidPlayer]:
        """Retrieves a player by assigned 3-digit number."""
        ...

    async def list_players(self, guild_id: str, alive_only: bool = False) -> List[SquidPlayer]:
        """Lists all enrolled players in a guild, optionally filtering by alive status."""
        ...

    async def get_next_available_number(self, guild_id: str) -> str:
        """Determines the next unassigned 3-digit player number (e.g. '001', '002')."""
        ...

    async def save_season(self, season: SquidSeason) -> None:
        """Persists or updates a season aggregate."""
        ...

    async def get_season(self, guild_id: str) -> Optional[SquidSeason]:
        """Retrieves active season state for a guild."""
        ...

    async def record_anomaly(self, anomaly: MovementAnomaly) -> None:
        """Records a movement violation or suspicious event."""
        ...

    async def atomic_eliminate_and_reward(
        self,
        player: SquidPlayer,
        season: SquidSeason
    ) -> None:
        """Atomically persists player elimination and increments season prize pool in a transaction."""
        ...
