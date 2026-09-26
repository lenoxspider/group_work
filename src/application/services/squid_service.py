"""
Squid Game application service.

What it does:
- Orchestrates player enrollment (001-456), elimination, and prize pot calculation.
- Manages Red Light Green Light minigame turns and movement evaluations.
- Synthesizes and pre-caches masked guard and doll voice audio for eliminations and game signals.
- Logs movement anomalies and enforces latency grace windows.

What it does NOT do:
- Does NOT execute direct Discord API calls or SQL statements directly.
"""

import time
import random
from datetime import datetime, timezone
from typing import Optional, Dict
from src.domain.entities.squid_player import SquidPlayer
from src.domain.entities.squid_season import SquidSeason
from src.domain.entities.movement_anomaly import MovementAnomaly
from src.domain.entities.guard_voice import GuardVoiceLines, GUARD_PROFILE, DOLL_PROFILE
from src.domain.interfaces.squid_repository import SquidRepository
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer
from src.domain.errors import EntityNotFoundError, ValidationError
from src.application.dtos.squid_dtos import (
    EnrollPlayerDTO,
    PlayerResultDTO,
    EliminationResultDTO,
    SquidStatusDTO,
    RedLightMoveDTO,
    RedLightMoveResultDTO
)

class SquidService:
    """Orchestrates Squid Game accountability rules and minigame flows."""

    def __init__(
        self,
        squid_repo: SquidRepository,
        synthesizer: Optional[SpeechSynthesizer] = None
    ):
        self.squid_repo = squid_repo
        self.synthesizer = synthesizer
        # In-memory active game state per guild: {guild_id: dict}
        self._active_games: Dict[str, dict] = {}
        # In-memory preloaded audio buffer cache
        self._audio_cache: Dict[str, bytes] = {}

    async def preload_audio_cache(self) -> None:
        """Pre-synthesizes standard audio cues into memory to eliminate runtime latency."""
        if not self.synthesizer:
            return
        cues = {
            "intro": (GuardVoiceLines.game_announcement("Red Light Green Light"), GUARD_PROFILE),
            "green_korean": (GuardVoiceLines.green_light_korean(), DOLL_PROFILE),
            "green_english": (GuardVoiceLines.green_light_english(), GUARD_PROFILE),
            "red": (GuardVoiceLines.red_light(), GUARD_PROFILE),
        }
        for key, (script, profile) in cues.items():
            try:
                audio = await self.synthesizer.synthesize(script, profile)
                if audio:
                    self._audio_cache[key] = audio
            except Exception:
                pass

    def get_cached_audio(self, key: str) -> Optional[bytes]:
        """Retrieves cached voice audio bytes if available."""
        return self._audio_cache.get(key)

    async def enroll_player(self, dto: EnrollPlayerDTO) -> PlayerResultDTO:
        """Enrolls a Discord member into the Squid Game roster with the next 3-digit tag."""
        if self.get_active_game(dto.guild_id):
            raise ValidationError("Arena doors are locked! A match is currently in progress. You cannot join mid-game.")

        existing = await self.squid_repo.get_player(dto.guild_id, dto.user_id)
        if existing:
            if not existing.is_alive:
                existing.revive()
                await self.squid_repo.save_player(existing)
            return self._to_player_dto(existing)

        number = await self.squid_repo.get_next_available_number(dto.guild_id)
        player = SquidPlayer(
            guild_id=dto.guild_id,
            user_id=dto.user_id,
            player_number=number
        )
        await self.squid_repo.save_player(player)
        return self._to_player_dto(player)

    async def get_player(self, guild_id: str, user_id: str) -> Optional[PlayerResultDTO]:
        """Looks up player by guild and Discord user ID."""
        player = await self.squid_repo.get_player(guild_id, user_id)
        return self._to_player_dto(player) if player else None

    async def eliminate_player(
        self,
        guild_id: str,
        user_id: str,
        reason: str,
        synthesize_audio: bool = True
    ) -> EliminationResultDTO:
        """Eliminates a player, updates the prize pot, and generates masked guard audio."""
        player = await self.squid_repo.get_player(guild_id, user_id)
        if not player:
            raise EntityNotFoundError(f"Player for user {user_id} not found in guild {guild_id}.")

        season = await self.squid_repo.get_season(guild_id)
        if not season:
            season = SquidSeason(guild_id=guild_id)

        if player.is_alive:
            player.eliminate(reason)
            season.record_elimination_bounty()
            await self.squid_repo.atomic_eliminate_and_reward(player, season)

        audio_bytes = None
        if self.synthesizer and synthesize_audio:
            script = GuardVoiceLines.elimination(player.spoken_number)
            try:
                audio_bytes = await self.synthesizer.synthesize(script, GUARD_PROFILE)
            except Exception:
                audio_bytes = None

        return EliminationResultDTO(
            guild_id=guild_id,
            user_id=user_id,
            player_number=player.player_number,
            display_tag=player.display_tag,
            reason=reason,
            pot_total=season.pot_amount,
            pot_formatted=season.formatted_pot,
            audio_bytes=audio_bytes
        )

    async def get_status(self, guild_id: str) -> SquidStatusDTO:
        """Computes server Squid Game metrics, survivors, and piggy bank total."""
        players = await self.squid_repo.list_players(guild_id)
        alive_count = sum(1 for p in players if p.is_alive)
        eliminated_count = len(players) - alive_count

        season = await self.squid_repo.get_season(guild_id)
        if not season:
            season = SquidSeason(guild_id=guild_id)

        return SquidStatusDTO(
            guild_id=guild_id,
            pot_formatted=season.formatted_pot,
            pot_amount=season.pot_amount,
            alive_count=alive_count,
            eliminated_count=eliminated_count,
            total_players=len(players),
            is_active=season.is_active,
            current_game=season.current_game
        )

    def start_red_light_game(self, guild_id: str, target: int = 100) -> None:
        """Starts a Red Light Green Light session for the guild."""
        self._active_games[guild_id] = {
            "light": "GREEN",
            "progress": {},
            "target": target,
            "finished": set(),
            "round": 1,
            "red_light_time": 0.0
        }

    def set_light(self, guild_id: str, light: str, round_num: Optional[int] = None) -> None:
        """Toggles the current doll signal (GREEN or RED) and marks timestamp."""
        clean_light = light.upper().strip()
        if clean_light not in {"GREEN", "RED"}:
            raise ValidationError(f"Invalid light state '{light}'. Must be 'GREEN' or 'RED'.")
        if guild_id in self._active_games:
            self._active_games[guild_id]["light"] = clean_light
            if clean_light == "RED":
                self._active_games[guild_id]["red_light_time"] = time.monotonic()
            if round_num is not None:
                self._active_games[guild_id]["round"] = round_num

    def get_light(self, guild_id: str) -> str:
        """Gets current light status."""
        game = self._active_games.get(guild_id)
        return game["light"] if game else "NONE"

    def get_active_game(self, guild_id: str) -> Optional[dict]:
        """Returns read-only copy of active game state."""
        return self._active_games.get(guild_id)

    def end_red_light_game(self, guild_id: str) -> None:
        """Terminates active session for guild."""
        self._active_games.pop(guild_id, None)

    def reset_all_games(self) -> None:
        """Resets all in-memory game sessions on bot reboot."""
        self._active_games.clear()

    async def timeout_slacking_players(self, guild_id: str) -> list[EliminationResultDTO]:
        """Eliminates all contestants who failed to reach the finish line before time expired."""
        game = self._active_games.get(guild_id)
        if not game:
            return []

        target = game.get("target", 100)
        progress = game.get("progress", {})
        finished_users = game.get("finished", set())

        alive_players = await self.squid_repo.list_players(guild_id, alive_only=True)
        eliminations = []
        for player in alive_players:
            if player.user_id not in finished_users and progress.get(player.user_id, 0) < target:
                res = await self.eliminate_player(
                    guild_id=guild_id,
                    user_id=player.user_id,
                    reason="Failed to reach the finish line in time",
                    synthesize_audio=False
                )
                eliminations.append(res)
        return eliminations

    async def revive_all_players(self, guild_id: str) -> int:
        """Restores all eliminated players to alive status for a fresh match."""
        return await self.squid_repo.revive_all_players(guild_id)

    async def reset_season(self, guild_id: str) -> None:
        """Resets the season bounty pot and restarts the game cycle."""
        await self.squid_repo.reset_season(guild_id)
        self.end_red_light_game(guild_id)

    async def get_active_racers(self, guild_id: str) -> list[SquidPlayer]:
        """Returns living contestants who have not yet crossed the finish line."""
        game = self._active_games.get(guild_id)
        if not game:
            return []
        finished_users = game.get("finished", set())
        alive_players = await self.squid_repo.list_players(guild_id, alive_only=True)
        return [p for p in alive_players if p.user_id not in finished_users]

    async def clear_session(self, guild_id: str) -> None:
        """Clears active session game state and resets contestant roster."""
        self.end_red_light_game(guild_id)
        await self.squid_repo.clear_players(guild_id)

    def _calculate_advance(self, round_num: int) -> int:
        """Dynamic step distance: narrows each round as tension increases."""
        base_min = max(5, 16 - (round_num - 1) * 2)
        base_max = max(12, 26 - (round_num - 1) * 2)
        return random.randint(base_min, base_max)

    async def process_move(self, dto: RedLightMoveDTO) -> RedLightMoveResultDTO:
        """Evaluates a /move attempt by an enrolled player with latency grace protection."""
        game = self._active_games.get(dto.guild_id)
        if not game:
            raise ValidationError("No Red Light Green Light game is currently active.")

        player = await self.squid_repo.get_player(dto.guild_id, dto.user_id)
        if not player:
            raise ValidationError("You are not enrolled in the games. Run /squid join first.")
        if not player.is_alive:
            raise ValidationError(f"{player.display_tag} is eliminated and cannot move.")

        if dto.user_id in game["finished"]:
            return RedLightMoveResultDTO(
                guild_id=dto.guild_id,
                user_id=dto.user_id,
                player_number=player.player_number,
                survived=True,
                distance=game["target"],
                is_finished=True,
                status_message=f"{player.display_tag} has already crossed the finish line!"
            )

        if game["light"] == "RED":
            red_start = game.get("red_light_time", 0.0)
            elapsed = time.monotonic() - red_start if red_start > 0 else 999.0
            if elapsed <= 0.5:
                # Latency grace period: record close-call anomaly but spare player
                anomaly = MovementAnomaly(
                    guild_id=dto.guild_id,
                    user_id=dto.user_id,
                    occurred_at=datetime.now(timezone.utc),
                    reason=f"Close call ({elapsed:.2f}s latency grace)"
                )
                await self.squid_repo.record_anomaly(anomaly)
                return RedLightMoveResultDTO(
                    guild_id=dto.guild_id,
                    user_id=dto.user_id,
                    player_number=player.player_number,
                    survived=True,
                    distance=game["progress"].get(dto.user_id, 0),
                    is_finished=False,
                    status_message=f"⚠️ Close call! Stopped within {elapsed:.2f}s grace window. Freeze immediately!"
                )

            # Red light elimination
            anomaly = MovementAnomaly(
                guild_id=dto.guild_id,
                user_id=dto.user_id,
                occurred_at=datetime.now(timezone.utc),
                reason=f"Moved during Red Light ({elapsed:.2f}s elapsed)"
            )
            await self.squid_repo.record_anomaly(anomaly)
            elim_result = await self.eliminate_player(
                guild_id=dto.guild_id,
                user_id=dto.user_id,
                reason="Moved during Red Light",
                synthesize_audio=True
            )
            return RedLightMoveResultDTO(
                guild_id=dto.guild_id,
                user_id=dto.user_id,
                player_number=player.player_number,
                survived=False,
                distance=game["progress"].get(dto.user_id, 0),
                is_finished=False,
                status_message="Movement detected during Red Light! You have been eliminated.",
                audio_bytes=elim_result.audio_bytes
            )

        # GREEN LIGHT -> Advance distance based on current round difficulty
        round_num = game.get("round", 1)
        advance = self._calculate_advance(round_num)
        current = game["progress"].get(dto.user_id, 0) + advance
        game["progress"][dto.user_id] = current

        is_finished = current >= game["target"]
        if is_finished:
            game["finished"].add(dto.user_id)
            player.advance_survival()
            await self.squid_repo.save_player(player)

        return RedLightMoveResultDTO(
            guild_id=dto.guild_id,
            user_id=dto.user_id,
            player_number=player.player_number,
            survived=True,
            distance=min(current, game["target"]),
            is_finished=is_finished,
            status_message=f"Advanced +{advance}m! Progress: {min(current, game['target'])}/{game['target']}m."
        )

    def _to_player_dto(self, player: SquidPlayer) -> PlayerResultDTO:
        return PlayerResultDTO(
            guild_id=player.guild_id,
            user_id=player.user_id,
            player_number=player.player_number,
            is_alive=player.is_alive,
            survival_streak=player.survival_streak,
            display_tag=player.display_tag
        )

