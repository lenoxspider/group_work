"""
Squid Game application Data Transfer Objects (DTOs).

What it does:
- Encapsulates structured parameters and results for Squid Game use cases.

What it does NOT do:
- Does NOT execute business logic or data transformations.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class EnrollPlayerDTO:
    """Request to enroll a Discord member as a numbered player."""
    guild_id: str
    user_id: str

@dataclass(frozen=True)
class PlayerResultDTO:
    """Read-only view of a player state."""
    guild_id: str
    user_id: str
    player_number: str
    is_alive: bool
    survival_streak: int
    display_tag: str

@dataclass(frozen=True)
class EliminationResultDTO:
    """Details returned after player elimination with pot update and optional guard audio."""
    guild_id: str
    user_id: str
    player_number: str
    display_tag: str
    reason: str
    pot_total: int
    pot_formatted: str
    audio_bytes: Optional[bytes] = None

@dataclass(frozen=True)
class SquidStatusDTO:
    """Summary dashboard of the server's Squid Game season."""
    guild_id: str
    pot_formatted: str
    pot_amount: int
    alive_count: int
    eliminated_count: int
    total_players: int
    is_active: bool
    current_game: str

@dataclass(frozen=True)
class RedLightMoveDTO:
    """Action payload when a player moves in Red Light Green Light."""
    guild_id: str
    user_id: str

@dataclass(frozen=True)
class RedLightMoveResultDTO:
    """Outcome of player move in Red Light Green Light."""
    guild_id: str
    user_id: str
    player_number: str
    survived: bool
    distance: int
    is_finished: bool
    status_message: str
    advance: int = 0
    target: int = 100
    rank: int = 1
    total_racers: int = 1
    is_rate_limited: bool = False
    status_code: str = "ok"
    audio_bytes: Optional[bytes] = None
