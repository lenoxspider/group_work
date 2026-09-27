"""Game module contract and registry.

The arena owns players, pot, elimination, voice, and votes. A Game only
declares its own rules and move handlers. Adding a game is registering a
new Game subclass in `get_games()`, never editing the arena.
"""

from typing import List


class Game:
    """Base contract every game module implements."""

    name: str = "unnamed"
    description: str = ""
    target: int = 100

    def __init__(self, arena):
        self.arena = arena

    def start(self, guild_id: str, event_id: str) -> None:
        raise NotImplementedError

    def is_active(self, guild_id: str) -> bool:
        return False

    def end(self, guild_id: str) -> None:
        raise NotImplementedError

    def reset_all(self) -> None:
        raise NotImplementedError

    def get_state(self, guild_id: str):
        return None

    async def handle_move(self, guild_id: str, user_id: str):
        raise NotImplementedError


def get_games(arena) -> List[Game]:
    """Return all registered game modules in play order."""
    from src.plugins.games.red_light import RedLightGreenLight

    return [RedLightGreenLight(arena)]