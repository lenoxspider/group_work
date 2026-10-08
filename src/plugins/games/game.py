"""Game module contract and registry.

The arena owns players, pot, elimination, voice, and votes. A Game only
declares its own rules and move handlers. Adding a game is registering a new
Game subclass in `get_games()`, never editing the arena.

Two interaction shapes exist:
- ``timed`` games (Red Light Green Light): moves are steps, judged by when they
  were made, so ``handle_move`` carries the click time.
- ``turn`` games (Glass Bridge): one player at a time picks a side, so
  ``handle_choice`` carries it, and ``handle_stall`` covers a player who never
  chose.
"""

from typing import List, Optional


class Game:
    """Base contract every game module implements."""

    name: str = "unnamed"
    description: str = ""
    target: int = 100
    kind: str = "timed"          # "timed" | "turn"
    default_rows: int = 8

    def __init__(self, arena):
        self.arena = arena

    def start(self, guild_id: str, event_id: str, players: Optional[List[str]] = None, **kwargs) -> None:
        raise NotImplementedError

    def is_active(self, guild_id: str) -> bool:
        return False

    def end(self, guild_id: str) -> None:
        raise NotImplementedError

    def reset_all(self) -> None:
        raise NotImplementedError

    def get_state(self, guild_id: str):
        return None

    # A step in a timed game (async - touches the arena's persistence).
    async def handle_move(self, guild_id: str, user_id: str, clicked_at=None):
        raise NotImplementedError

    # A choice in a turn game (sync - pure logic; the runner owns any I/O).
    def handle_choice(self, guild_id: str, user_id: str, side: str):
        raise NotImplementedError

    # A player who never chose within the turn window.
    def handle_stall(self, guild_id: str):
        return None


def get_games(arena) -> List[Game]:
    """Return all registered game modules in play order."""
    from src.plugins.games.glass_bridge import GlassBridge
    from src.plugins.games.red_light import RedLightGreenLight

    return [RedLightGreenLight(arena), GlassBridge(arena)]
