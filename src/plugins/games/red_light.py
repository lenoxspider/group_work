"""Red Light Green Light game module (round 1).

An in-memory state machine: move on GREEN, freeze on RED. Any movement
during RED_LIGHT outside the latency grace window eliminates the player.
Elimination is delegated to the arena, which owns the roster and pot.
"""

import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, List, Optional

from src.plugins.games.game import Game

# Grace after the light flips, judged by when the player clicked rather than
# when the bot received the click. Sized for real Discord latency: edit
# propagation + human reaction. The sprint trade-off is preserved - a tighter
# window - but 0.2s was only ever winnable on a perfect connection.
GRACE_SECONDS = 1.5
SPRINT_GRACE_SECONDS = 0.8


@dataclass(frozen=True)
class MoveResult:
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


class RedLightGreenLight(Game):
    name = "Red Light Green Light"
    description = "Move on green light, freeze on red. Move on red and you are eliminated."

    def __init__(
        self,
        arena,
        clock: Optional[Callable[[], float]] = None,
        rng: Optional[random.Random] = None,
        wall_clock: Optional[Callable[[], datetime]] = None,
    ):
        super().__init__(arena)
        self.clock = clock or time.monotonic
        self.wall_clock = wall_clock or (lambda: datetime.now(timezone.utc))
        self.rng = rng or random.Random()
        self._active_games: dict = {}

    def start(self, guild_id: str, event_id: str, target: int = 100) -> None:
        self._active_games[guild_id] = {
            "event_id": event_id,
            "light": "GREEN",
            "progress": {},
            "target": target,
            "finished": set(),
            "round": 1,
            "red_light_time": 0.0,
            "red_light_wall": None,
            "round_moves": {},
            "sprinting": set(),
            "last_taps": {},
            "eliminated_this_round": [],
            "board_dirty": True,
        }

    def set_light(self, guild_id: str, light: str, round_num: Optional[int] = None) -> None:
        clean = light.upper().strip()
        if clean not in {"GREEN", "RED"}:
            raise ValueError(f"Invalid light state '{light}'. Must be 'GREEN' or 'RED'.")
        game = self._active_games.get(guild_id)
        if not game:
            return
        game["light"] = clean
        game["board_dirty"] = True
        if clean == "RED":
            game["red_light_time"] = self.clock()
            game["red_light_wall"] = self.wall_clock()
            game["eliminated_this_round"] = []
        else:
            game["round_moves"] = {}
            game["sprinting"] = set()
        if round_num is not None:
            game["round"] = round_num

    def get_light(self, guild_id: str) -> str:
        game = self._active_games.get(guild_id)
        return game["light"] if game else "NONE"

    def is_active(self, guild_id: str) -> bool:
        return guild_id in self._active_games

    def get_state(self, guild_id: str) -> Optional[dict]:
        return self._active_games.get(guild_id)

    def end(self, guild_id: str) -> None:
        self._active_games.pop(guild_id, None)

    def reset_all(self) -> None:
        self._active_games.clear()

    def _event_id(self, guild_id: str) -> Optional[str]:
        game = self._active_games.get(guild_id)
        return game.get("event_id") if game else None

    async def get_active_racers(self, guild_id: str):
        game = self._active_games.get(guild_id)
        if not game:
            return []
        event_id = game.get("event_id")
        finished = game.get("finished", set())
        alive = await self.arena.repo.list_players(guild_id, event_id, alive_only=True)
        return [p for p in alive if p.user_id not in finished]

    def _calculate_advance(self, round_num: int) -> int:
        base_min = max(5, 16 - (round_num - 1) * 2)
        base_max = max(12, 26 - (round_num - 1) * 2)
        return self.rng.randint(base_min, base_max)

    def _click_wall(self, clicked_at: Optional[datetime]) -> datetime:
        """The player's click as a wall-clock time.

        Discord stamps interactions when the user clicks, so this is earlier than
        bot-receipt time and is the honest moment to judge a red-light move
        against. Naive values are assumed to be UTC.
        """
        if clicked_at is None:
            return self.wall_clock()
        if clicked_at.tzinfo is None:
            return clicked_at.replace(tzinfo=timezone.utc)
        return clicked_at

    async def handle_move(self, guild_id: str, user_id: str, clicked_at: Optional[datetime] = None) -> MoveResult:
        game = self._active_games.get(guild_id)
        if not game:
            raise ValueError("No Red Light Green Light game is currently active.")

        event_id = game.get("event_id")
        player = await self.arena.repo.get_player(guild_id, event_id, user_id)
        if not player:
            raise ValueError("You are not enrolled in this event.")
        if not player.is_alive:
            raise ValueError(f"{player.display_tag} is eliminated and cannot move.")

        if user_id in game["finished"]:
            return MoveResult(
                guild_id=guild_id, user_id=user_id, player_number=player.player_number,
                survived=True, distance=game["target"], is_finished=True,
                status_code="finished",
                status_message=f"{player.display_tag} has already crossed the finish line!",
            )

        now = self.clock()
        last_taps = game.setdefault("last_taps", {})
        if now - last_taps.get(user_id, 0.0) < 0.5:
            return MoveResult(
                guild_id=guild_id, user_id=user_id, player_number=player.player_number,
                survived=True, distance=game["progress"].get(user_id, 0), is_finished=False,
                is_rate_limited=True, status_code="double_tap",
                status_message="Double-tap ignored. Only one tap per 0.5s is registered.",
            )
        last_taps[user_id] = now

        if game["light"] == "RED":
            return await self._eval_red_move(game, player, event_id, guild_id, user_id, self._click_wall(clicked_at))
        return await self._eval_green_move(game, player, guild_id, user_id)

    async def _eval_red_move(self, game, player, event_id, guild_id, user_id, clicked_at: datetime) -> MoveResult:
        red_wall = game.get("red_light_wall")
        is_sprinting = user_id in game.get("sprinting", set())
        grace_window = SPRINT_GRACE_SECONDS if is_sprinting else GRACE_SECONDS

        if red_wall is None:
            # No recorded flip (a game started before this landed). Never
            # eliminate on missing data.
            elapsed = 0.0
        else:
            elapsed = (clicked_at - red_wall).total_seconds()

        # A negative elapsed means the click was made before the light flipped
        # server-side - the player saw green - so it is safe by definition.
        shown = max(elapsed, 0.0)

        if elapsed <= grace_window:
            await self.arena.repo.record_anomaly(
                guild_id, event_id, user_id,
                f"Close call ({shown:.2f}s after the flip by click time, sprint={is_sprinting})",
            )
            penalty_note = (
                f" Sprint momentum shrinks that window to {SPRINT_GRACE_SECONDS}s."
                if is_sprinting else ""
            )
            return MoveResult(
                guild_id=guild_id, user_id=user_id, player_number=player.player_number,
                survived=True, distance=game["progress"].get(user_id, 0), is_finished=False,
                status_code="grace",
                status_message=f"Close call! Your move landed {shown:.2f}s after the red light.{penalty_note} Freeze immediately!",
            )

        await self.arena.repo.record_anomaly(
            guild_id, event_id, user_id,
            f"Moved during Red Light ({shown:.2f}s after the flip by click time, sprint={is_sprinting})",
        )
        audio_bytes = None
        elim_res = await self.arena.eliminate_player(guild_id, user_id, "Moved during Red Light")
        if elim_res:
            audio_bytes = elim_res.audio_bytes
        game.setdefault("eliminated_this_round", []).append(user_id)
        game["board_dirty"] = True
        return MoveResult(
            guild_id=guild_id, user_id=user_id, player_number=player.player_number,
            survived=False, distance=game["progress"].get(user_id, 0), is_finished=False,
            status_code="eliminated",
            status_message=(
                f"Movement detected {shown:.2f}s after the red light"
                + (f" (sprint momentum shrinks the grace window to {SPRINT_GRACE_SECONDS}s)" if is_sprinting else "")
                + ". You have been eliminated."
            ),
            audio_bytes=audio_bytes,
        )

    async def _eval_green_move(self, game, player, guild_id, user_id) -> MoveResult:
        round_moves = game.setdefault("round_moves", {})
        moves_count = round_moves.get(user_id, 0)
        if moves_count >= 2:
            return MoveResult(
                guild_id=guild_id, user_id=user_id, player_number=player.player_number,
                survived=True, distance=game["progress"].get(user_id, 0), is_finished=False,
                status_code="sprint_limit",
                status_message="Sprint limit reached for this round! Freeze and wait for the next light.",
            )

        round_num = game.get("round", 1)
        base_advance = self._calculate_advance(round_num)
        if moves_count == 0:
            advance = base_advance
            round_moves[user_id] = 1
            status_intro = f"Safe step! +{advance}m."
        else:
            advance = base_advance + 5
            round_moves[user_id] = 2
            game.setdefault("sprinting", set()).add(user_id)
            status_intro = f"Sprint burst! +{advance}m (Stopping is harder!)."

        current = game["progress"].get(user_id, 0) + advance
        game["progress"][user_id] = current
        game["board_dirty"] = True

        is_finished = current >= game["target"]
        if is_finished:
            game["finished"].add(user_id)
            player.advance_survival()
            await self.arena.repo.save_player(player)

        all_racers = sorted(game["progress"].items(), key=lambda x: x[1], reverse=True)
        rank = next((idx + 1 for idx, (u, _) in enumerate(all_racers) if u == user_id), 1)

        return MoveResult(
            guild_id=guild_id, user_id=user_id, player_number=player.player_number,
            survived=True, distance=min(current, game["target"]), is_finished=is_finished,
            advance=advance, target=game["target"], rank=rank, total_racers=len(all_racers),
            status_code="ok",
            status_message=f"{status_intro} Progress: {min(current, game['target'])}/{game['target']}m.",
        )