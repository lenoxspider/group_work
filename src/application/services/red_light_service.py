"""
Red Light Green Light minigame application service.

What it does:
- Manages in-memory minigame session state (light, target, round, progress, finishes).
- Evaluates contestant movement with rate-limiting, latency grace, and sprint mechanics.
- Injects clock and RNG for deterministic zero-latency simulation.

What it does NOT do:
- Does NOT interact directly with Discord API.
- Does NOT execute direct SQL queries.
"""

import time
import random
from datetime import datetime, timezone
from typing import Optional, Dict, Callable, List
from src.domain.entities.squid_player import SquidPlayer
from src.domain.entities.movement_anomaly import MovementAnomaly
from src.domain.interfaces.squid_repository import SquidRepository
from src.domain.errors import ValidationError
from src.application.dtos.squid_dtos import RedLightMoveResultDTO

class RedLightService:
    """Manages active Red Light Green Light sessions and move evaluations."""

    def __init__(
        self,
        squid_repo: SquidRepository,
        clock: Optional[Callable[[], float]] = None,
        rng: Optional[random.Random] = None,
        eliminate_callback: Optional[Callable] = None
    ):
        self.squid_repo = squid_repo
        self.clock = clock or time.monotonic
        self.rng = rng or random.Random()
        self.eliminate_callback = eliminate_callback
        self._active_games: Dict[str, dict] = {}

    def start_game(self, guild_id: str, target: int = 100) -> None:
        """Initializes a new match state."""
        self._active_games[guild_id] = {
            "light": "GREEN",
            "progress": {},
            "target": target,
            "finished": set(),
            "round": 1,
            "red_light_time": 0.0,
            "round_moves": {},
            "sprinting": set(),
            "last_taps": {},
            "eliminated_this_round": [],
            "board_dirty": True
        }

    def set_light(self, guild_id: str, light: str, round_num: Optional[int] = None) -> None:
        """Toggles signal (GREEN/RED) and resets phase states."""
        clean_light = light.upper().strip()
        if clean_light not in {"GREEN", "RED"}:
            raise ValidationError(f"Invalid light state '{light}'. Must be 'GREEN' or 'RED'.")
        if guild_id in self._active_games:
            game = self._active_games[guild_id]
            game["light"] = clean_light
            game["board_dirty"] = True
            if clean_light == "RED":
                game["red_light_time"] = self.clock()
                game["eliminated_this_round"] = []
            elif clean_light == "GREEN":
                game["round_moves"] = {}
                game["sprinting"] = set()
            if round_num is not None:
                game["round"] = round_num

    def get_light(self, guild_id: str) -> str:
        game = self._active_games.get(guild_id)
        return game["light"] if game else "NONE"

    def get_active_game(self, guild_id: str) -> Optional[dict]:
        return self._active_games.get(guild_id)

    def end_game(self, guild_id: str) -> None:
        self._active_games.pop(guild_id, None)

    def reset_all_games(self) -> None:
        self._active_games.clear()

    async def get_active_racers(self, guild_id: str) -> List[SquidPlayer]:
        """Living contestants not yet across finish line."""
        game = self._active_games.get(guild_id)
        if not game:
            return []
        finished = game.get("finished", set())
        alive = await self.squid_repo.list_players(guild_id, alive_only=True)
        return [p for p in alive if p.user_id not in finished]

    def _calculate_advance(self, round_num: int) -> int:
        base_min = max(5, 16 - (round_num - 1) * 2)
        base_max = max(12, 26 - (round_num - 1) * 2)
        return self.rng.randint(base_min, base_max)

    async def handle_move(self, guild_id: str, user_id: str) -> RedLightMoveResultDTO:
        """Evaluates move attempt with guard sequence 1.5."""
        game = self._active_games.get(guild_id)
        if not game:
            raise ValidationError("No Red Light Green Light game is currently active.")

        player = await self.squid_repo.get_player(guild_id, user_id)
        if not player:
            raise ValidationError("You are not enrolled in the games. Run /squid join first.")
        if not player.is_alive:
            raise ValidationError(f"{player.display_tag} is eliminated and cannot move.")

        if user_id in game["finished"]:
            return RedLightMoveResultDTO(
                guild_id=guild_id,
                user_id=user_id,
                player_number=player.player_number,
                survived=True,
                distance=game["target"],
                is_finished=True,
                status_code="finished",
                status_message=f"{player.display_tag} has already crossed the finish line!"
            )

        now = self.clock()
        last_taps = game.setdefault("last_taps", {})
        if now - last_taps.get(user_id, 0.0) < 0.5:
            return RedLightMoveResultDTO(
                guild_id=guild_id,
                user_id=user_id,
                player_number=player.player_number,
                survived=True,
                distance=game["progress"].get(user_id, 0),
                is_finished=False,
                is_rate_limited=True,
                status_code="double_tap",
                status_message="⚠️ Double-tap ignored. Only one tap per 0.5s is registered."
            )
        last_taps[user_id] = now

        if game["light"] == "RED":
            return await self._eval_red_move(game, player, guild_id, user_id, now)
        return await self._eval_green_move(game, player, guild_id, user_id)

    async def _eval_red_move(
        self, game: dict, player: SquidPlayer, guild_id: str, user_id: str, now: float
    ) -> RedLightMoveResultDTO:
        red_start = game.get("red_light_time", 0.0)
        elapsed = now - red_start if red_start > 0 else 999.0
        is_sprinting = user_id in game.get("sprinting", set())
        grace_window = 0.2 if is_sprinting else 0.5

        if elapsed <= grace_window:
            anomaly = MovementAnomaly(
                guild_id=guild_id,
                user_id=user_id,
                occurred_at=datetime.now(timezone.utc),
                reason=f"Close call ({elapsed:.2f}s latency grace, sprint={is_sprinting})"
            )
            await self.squid_repo.record_anomaly(anomaly)
            penalty_note = " (Sprint momentum: 0.2s grace)" if is_sprinting else ""
            return RedLightMoveResultDTO(
                guild_id=guild_id,
                user_id=user_id,
                player_number=player.player_number,
                survived=True,
                distance=game["progress"].get(user_id, 0),
                is_finished=False,
                status_code="grace",
                status_message=f"⚠️ Close call! Stopped within {elapsed:.2f}s grace window{penalty_note}. Freeze immediately!"
            )

        anomaly = MovementAnomaly(
            guild_id=guild_id,
            user_id=user_id,
            occurred_at=datetime.now(timezone.utc),
            reason=f"Moved during Red Light ({elapsed:.2f}s elapsed, sprint={is_sprinting})"
        )
        await self.squid_repo.record_anomaly(anomaly)
        audio_bytes = None
        if self.eliminate_callback:
            elim_res = await self.eliminate_callback(guild_id, user_id, "Moved during Red Light")
            audio_bytes = elim_res.audio_bytes
        game.setdefault("eliminated_this_round", []).append(user_id)
        game["board_dirty"] = True
        return RedLightMoveResultDTO(
            guild_id=guild_id,
            user_id=user_id,
            player_number=player.player_number,
            survived=False,
            distance=game["progress"].get(user_id, 0),
            is_finished=False,
            status_code="eliminated",
            status_message="Movement detected during Red Light! You have been eliminated.",
            audio_bytes=audio_bytes
        )

    async def _eval_green_move(
        self, game: dict, player: SquidPlayer, guild_id: str, user_id: str
    ) -> RedLightMoveResultDTO:
        round_moves = game.setdefault("round_moves", {})
        moves_count = round_moves.get(user_id, 0)
        if moves_count >= 2:
            return RedLightMoveResultDTO(
                guild_id=guild_id,
                user_id=user_id,
                player_number=player.player_number,
                survived=True,
                distance=game["progress"].get(user_id, 0),
                is_finished=False,
                status_code="sprint_limit",
                status_message="⚠️ Sprint limit reached for this round! Freeze and wait for the next light."
            )

        round_num = game.get("round", 1)
        base_advance = self._calculate_advance(round_num)
        if moves_count == 0:
            advance = base_advance
            round_moves[user_id] = 1
            status_intro = f"👣 Safe step! +{advance}m."
        else:
            advance = base_advance + 5
            round_moves[user_id] = 2
            game.setdefault("sprinting", set()).add(user_id)
            status_intro = f"⚡ Sprint burst! +{advance}m (Stopping is harder!)."

        current = game["progress"].get(user_id, 0) + advance
        game["progress"][user_id] = current
        game["board_dirty"] = True

        is_finished = current >= game["target"]
        if is_finished:
            game["finished"].add(user_id)
            player.advance_survival()
            await self.squid_repo.save_player(player)

        all_racers = sorted(game["progress"].items(), key=lambda x: x[1], reverse=True)
        rank = next((idx + 1 for idx, (u, _) in enumerate(all_racers) if u == user_id), 1)

        return RedLightMoveResultDTO(
            guild_id=guild_id,
            user_id=user_id,
            player_number=player.player_number,
            survived=True,
            distance=min(current, game["target"]),
            is_finished=is_finished,
            advance=advance,
            target=game["target"],
            rank=rank,
            total_racers=len(all_racers),
            status_code="ok",
            status_message=f"{status_intro} Progress: {min(current, game['target'])}/{game['target']}m."
        )
