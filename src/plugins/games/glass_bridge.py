"""Glass Bridge game module.

A turn-based, choice-based game - deliberately the opposite of Red Light Green
Light. There is no timing and no latency to worry about: players cross a bridge
of glass panels one at a time, each row offering Left or Right, exactly one of
which is tempered.

The mechanic that makes it dramatic is the one from the show: a panel someone
dies on is then *known* to everyone who follows, so the players at the back of
the queue owe their lives to the ones who went first. The first mover is the
most likely to fall.

Model: ``order`` is a queue and ``order[0]`` is always the current player, who
keeps stepping until they fall or reach the far side. A player's row position
resets to zero when a new one starts; what the bridge knows does not.

Pure logic, no Discord and no time - those live in the runner and the view.
"""

import random
from dataclasses import dataclass
from typing import List, Optional


class NotYourTurn(Exception):
    """Raised when a player tries to move out of turn."""


class NoActiveBridge(Exception):
    """Raised when a move is made with no bridge running for the guild."""


# Outcomes of a single choice.
STEPPED_SAFE = "safe"      # right panel, advance
FELL = "fell"              # wrong panel, eliminated
CROSSED = "crossed"        # right panel on the final row, survived the bridge
STALLED = "stalled"        # chose nothing within the turn window


@dataclass(frozen=True)
class BridgeMove:
    guild_id: str
    user_id: str
    outcome: str
    row: int
    side: str
    bridge_done: bool
    current_player: Optional[str]      # the next player to move, if any
    players_left: int


class GlassBridge:
    """One bridge crossing for one guild at a time."""

    name = "Glass Bridge"
    description = (
        "Cross the glass bridge one at a time. Each row, pick left or right - "
        "one panel is tempered, one is false. A panel someone dies on is known "
        "to everyone behind them."
    )

    def __init__(self, rng: Optional[random.Random] = None):
        self.rng = rng or random.Random()
        self._bridges: dict = {}

    @staticmethod
    def sides() -> List[str]:
        return ["left", "right"]

    def start(self, guild_id: str, players: List[str], rows: int = 8) -> None:
        """players are in crossing order - the front of the queue moves first."""
        if not players:
            raise ValueError("A bridge needs at least one player.")
        self._bridges[guild_id] = {
            "guild_id": guild_id,
            "order": list(players),
            "players": list(players),
            "rows": rows,
            # safe[row] is "left" or "right"; the true layout
            "safe": [self.rng.choice(self.sides()) for _ in range(rows)],
            # known[row] is None until a panel in that row has been tried
            "known": [None] * rows,
            "current_row": 0,
            "fell": [],
            "crossed": [],
            "done": False,
        }

    def is_active(self, guild_id: str) -> bool:
        return guild_id in self._bridges

    def end(self, guild_id: str) -> None:
        self._bridges.pop(guild_id, None)

    def get_state(self, guild_id: str) -> Optional[dict]:
        return self._bridges.get(guild_id)

    def reset_all(self) -> None:
        self._bridges.clear()

    def current_player(self, guild_id: str) -> Optional[str]:
        bridge = self._bridges.get(guild_id)
        if not bridge or bridge["done"] or not bridge["order"]:
            return None
        return bridge["order"][0]

    def _resolve(self, bridge: dict, user_id: str, row: int, side: str, outcome: str) -> BridgeMove:
        bridge["done"] = not bridge["order"]
        return BridgeMove(
            guild_id=bridge["guild_id"],
            user_id=user_id,
            outcome=outcome,
            row=row,
            side=side,
            bridge_done=bridge["done"],
            current_player=self.current_player(bridge["guild_id"]),
            players_left=len(bridge["order"]),
        )

    def handle_move(self, guild_id: str, user_id: str, side: str) -> BridgeMove:
        bridge = self._bridges.get(guild_id)
        if not bridge or bridge["done"]:
            raise NoActiveBridge("No bridge is running here.")
        side = (side or "").strip().lower()
        if side not in ("left", "right"):
            raise ValueError("Choose 'left' or 'right'.")
        if not bridge["order"]:
            raise NoActiveBridge("The crossing is over.")
        if user_id != bridge["order"][0]:
            raise NotYourTurn("It is not your move.")

        row = bridge["current_row"]
        bridge["known"][row] = bridge["safe"][row]  # trying the row reveals it either way

        if side == bridge["safe"][row]:
            bridge["current_row"] += 1
            if bridge["current_row"] >= bridge["rows"]:
                bridge["crossed"].append(user_id)
                bridge["order"].pop(0)
                bridge["current_row"] = 0
                outcome = CROSSED
            else:
                outcome = STEPPED_SAFE
        else:
            bridge["fell"].append(user_id)
            bridge["order"].pop(0)
            bridge["current_row"] = 0
            outcome = FELL

        return self._resolve(bridge, user_id, row, side, outcome)

    def handle_stall(self, guild_id: str) -> Optional[BridgeMove]:
        """The current player failed to choose in time. They fall."""
        bridge = self._bridges.get(guild_id)
        if not bridge or bridge["done"] or not bridge["order"]:
            return None
        user_id = bridge["order"][0]
        row = bridge["current_row"]
        bridge["fell"].append(user_id)
        bridge["order"].pop(0)
        bridge["current_row"] = 0
        return self._resolve(bridge, user_id, row, "none", STALLED)

    def board(self, guild_id: str) -> Optional[dict]:
        """A renderable snapshot: rows, what is known, and who stands where."""
        bridge = self._bridges.get(guild_id)
        if not bridge:
            return None
        return {
            "rows": bridge["rows"],
            "known": list(bridge["known"]),
            "current_row": bridge["current_row"],
            "current_player": self.current_player(guild_id),
            "queue": list(bridge["order"]),
            "fell": list(bridge["fell"]),
            "crossed": list(bridge["crossed"]),
            "done": bridge["done"],
        }
