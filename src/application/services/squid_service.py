"""
Squid Game application service.

What it does:
- Orchestrates player enrollment (001-456), elimination, and prize pot calculation.
- Manages Red Light Green Light minigame turns and movement evaluations.
- Synthesizes masked guard and doll voice audio for eliminations and game signals.

What it does NOT do:
- Does NOT execute direct Discord API calls or SQL statements directly.
"""

import random
from typing import Optional, Dict
from src.domain.entities.squid_player import SquidPlayer
from src.domain.entities.squid_season import SquidSeason
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
        # In-memory active game state per guild: {guild_id: {"light": "GREEN", "progress": {user_id: int}, "target": 100}}
        self._active_games: Dict[str, dict] = {}

    async def enroll_player(self, dto: EnrollPlayerDTO) -> PlayerResultDTO:
        """Enrolls a Discord member into the Squid Game roster with the next 3-digit tag."""
        existing = await self.squid_repo.get_player(dto.guild_id, dto.user_id)
        if existing:
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
            await self.squid_repo.save_player(player)
            await self.squid_repo.save_season(season)

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
            "finished": set()
        }

    def set_light(self, guild_id: str, light: str) -> None:
        """Toggles the current doll signal (GREEN or RED)."""
        clean_light = light.upper().strip()
        if clean_light not in {"GREEN", "RED"}:
            raise ValidationError(f"Invalid light state '{light}'. Must be 'GREEN' or 'RED'.")
        if guild_id in self._active_games:
            self._active_games[guild_id]["light"] = clean_light

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

    async def process_move(self, dto: RedLightMoveDTO) -> RedLightMoveResultDTO:
        """Evaluates a /move attempt by an enrolled player."""
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
            # Player moved during RED LIGHT -> Eliminate!
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

        # GREEN LIGHT -> Advance distance
        advance = random.randint(15, 25)
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
