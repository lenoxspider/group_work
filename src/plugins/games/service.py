"""Games arena application service.

Owns the event lifecycle, entry-fee pot escrow, elimination, voting, and
payout. The arena is game-agnostic: it delegates round execution to the
registered Game (round 1 = Red Light Green Light) and never hardcodes a
specific game's rules.
"""

import random
import time
import uuid
from dataclasses import dataclass
from typing import Callable, List, Optional

from src.domain.errors import EntityNotFoundError, ValidationError
from src.plugins.bank.domain import InsufficientFunds, POT as POT_ACCOUNT
from src.plugins.games.domain import (
    CONCLUDED,
    DEFAULT_ENTRY_FEE,
    ONGOING,
    REGISTERING,
    Event,
    GuardVoiceLines,
    GUARD_PROFILE,
    DOLL_PROFILE,
    Player,
    Vote,
    utcnow,
)
from src.plugins.games.game import Game, get_games
from src.plugins.games.repository import SQLiteGamesRepository


@dataclass(frozen=True)
class EliminationResult:
    guild_id: str
    user_id: str
    player_number: str
    display_tag: str
    reason: str
    pot_total: int
    pot_formatted: str
    audio_bytes: Optional[bytes] = None


@dataclass(frozen=True)
class StatusResult:
    guild_id: str
    status: str
    pot_amount: int
    pot_formatted: str
    alive_count: int
    eliminated_count: int
    total_players: int
    current_game: str
    entry_fee: int


@dataclass(frozen=True)
class ConcludeResult:
    guild_id: str
    status: str
    winner_id: Optional[str]
    survivor_count: int
    pot_total: int
    pot_formatted: str
    payout_per_survivor: int


class ArenaService:
    def __init__(
        self,
        repo: SQLiteGamesRepository,
        synthesizer=None,
        clock: Optional[Callable[[], float]] = None,
        rng: Optional[random.Random] = None,
    ):
        self.repo = repo
        self.synthesizer = synthesizer
        self.bank = None
        self.clock = clock or time.monotonic
        self.rng = rng or random.Random()
        self.games: List[Game] = get_games(self)
        for game in self.games:
            game.clock = self.clock
            game.rng = self.rng
        self.game = self.games[0] if self.games else None
        self._audio_cache: dict = {}

    def attach_bank(self, bank) -> None:
        self.bank = bank

    @property
    def current_game_name(self) -> str:
        return self.game.name if self.game else "None"

    # --- Audio cache ---

    async def preload_audio_cache(self) -> None:
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
        return self._audio_cache.get(key)

    # --- Event lifecycle ---

    async def open_event(self, guild_id: str, entry_fee: Optional[int] = None) -> Event:
        active = await self.repo.get_active_event(guild_id)
        if active:
            raise ValidationError("An event is already in progress. Conclude it first.")
        fee = DEFAULT_ENTRY_FEE if entry_fee is None else max(0, entry_fee)
        event = Event(
            event_id=f"EV-{uuid.uuid4().hex[:8].upper()}",
            guild_id=guild_id,
            status=REGISTERING,
            entry_fee=fee,
        )
        await self.repo.save_event(event)
        return event

    async def get_active_event(self, guild_id: str) -> Optional[Event]:
        return await self.repo.get_active_event(guild_id)

    async def join_event(self, guild_id: str, user_id: str) -> Player:
        event = await self.repo.get_active_event(guild_id)
        if not event:
            raise ValidationError("No open event. Run /event open first.")
        if event.status != REGISTERING:
            raise ValidationError("Registration is closed for this event.")

        existing = await self.repo.get_player(guild_id, event.event_id, user_id)
        if existing:
            return existing

        fee = event.entry_fee
        if self.bank and fee > 0:
            try:
                await self.bank.transfer(guild_id, user_id, POT_ACCOUNT, fee, "arena entry fee")
            except InsufficientFunds:
                raise ValidationError(f"You need {fee} spi to join the games.") from None
            event.pot_amount += fee
            await self.repo.save_event(event)

        number = await self.repo.get_next_number(guild_id, event.event_id)
        player = Player(guild_id=guild_id, event_id=event.event_id, user_id=user_id, player_number=number)
        await self.repo.save_player(player)
        return player

    async def start_event(self, guild_id: str) -> Event:
        event = await self.repo.get_active_event(guild_id)
        if not event:
            raise ValidationError("No event to start. Run /event open first.")
        if event.status != REGISTERING:
            raise ValidationError("Event is already underway.")

        alive = await self.repo.list_players(guild_id, event.event_id, alive_only=True)
        if not alive:
            raise ValidationError("At least one player must join before starting.")

        event.begin()
        await self.repo.save_event(event)
        if self.game:
            self.game.start(guild_id, event.event_id, target=self.game.target)
        return event

    # --- Elimination (game-driven, event-scoped) ---

    async def eliminate_player(
        self, guild_id: str, user_id: str, reason: str, synthesize_audio: bool = True
    ) -> Optional[EliminationResult]:
        event = await self.repo.get_active_event(guild_id)
        if not event:
            raise EntityNotFoundError("No active event.")
        player = await self.repo.get_player(guild_id, event.event_id, user_id)
        if not player:
            raise EntityNotFoundError(f"User {user_id} is not enrolled in this event.")

        was_alive = player.is_alive
        if was_alive:
            player.eliminate(reason)
            await self.repo.save_player(player)

        audio_bytes = None
        if self.synthesizer and synthesize_audio and was_alive:
            try:
                audio_bytes = await self.synthesizer.synthesize(
                    GuardVoiceLines.elimination(player.spoken_number), GUARD_PROFILE
                )
            except Exception:
                audio_bytes = None

        return EliminationResult(
            guild_id=guild_id,
            user_id=user_id,
            player_number=player.player_number,
            display_tag=player.display_tag,
            reason=reason,
            pot_total=event.pot_amount,
            pot_formatted=event.formatted_pot,
            audio_bytes=audio_bytes,
        )

    async def timeout_slacking_players(self, guild_id: str) -> List[EliminationResult]:
        event = await self.repo.get_active_event(guild_id)
        if not event or not self.game:
            return []
        state = self.game.get_state(guild_id)
        if not state:
            return []

        target = state.get("target", 100)
        progress = state.get("progress", {})
        finished = state.get("finished", set())

        alive = await self.repo.list_players(guild_id, event.event_id, alive_only=True)
        eliminations = []
        for player in alive:
            if player.user_id not in finished and progress.get(player.user_id, 0) < target:
                res = await self.eliminate_player(
                    guild_id, player.user_id, "Failed to reach the finish line in time",
                    synthesize_audio=False,
                )
                if res:
                    eliminations.append(res)
        return eliminations

    # --- Voting (scaffolded for when game 2+ lands) ---

    async def open_voting(self, guild_id: str) -> Event:
        event = await self.repo.get_active_event(guild_id)
        if not event:
            raise ValidationError("No active event.")
        event.status = "VOTING"
        await self.repo.save_event(event)
        await self.repo.clear_votes(guild_id, event.event_id)
        return event

    async def vote(self, guild_id: str, user_id: str, choice: str) -> Vote:
        event = await self.repo.get_active_event(guild_id)
        if not event:
            raise ValidationError("No active event.")
        if event.status != "VOTING":
            raise ValidationError("Voting is not open right now.")
        choice = choice.lower().strip()
        if choice not in ("continue", "stop"):
            raise ValidationError("Choice must be 'continue' or 'stop'.")
        player = await self.repo.get_player(guild_id, event.event_id, user_id)
        if not player or not player.is_alive:
            raise ValidationError("You are not a surviving player in this event.")

        vote = Vote(guild_id=guild_id, event_id=event.event_id, user_id=user_id, choice=choice, voted_at=utcnow())
        await self.repo.record_vote(vote)
        return vote

    # --- Payout ---

    async def conclude_event(self, guild_id: str) -> ConcludeResult:
        event = await self.repo.get_active_event(guild_id)
        if not event:
            raise ValidationError("No active event to conclude.")

        survivors = await self.repo.list_players(guild_id, event.event_id, alive_only=True)
        pot = event.pot_amount

        winner_id: Optional[str] = None
        payout_per = 0
        if len(survivors) == 1:
            winner_id = survivors[0].user_id
            payout_per = pot
            if pot > 0 and self.bank:
                await self.bank.transfer(guild_id, POT_ACCOUNT, winner_id, pot, "arena payout")
        elif len(survivors) > 1 and pot > 0 and self.bank:
            base = pot // len(survivors)
            remainder = pot % len(survivors)
            for i, player in enumerate(survivors):
                share = base + (remainder if i == len(survivors) - 1 else 0)
                await self.bank.transfer(guild_id, POT_ACCOUNT, player.user_id, share, "arena payout")
            payout_per = base
        elif len(survivors) > 1:
            payout_per = pot // len(survivors)

        # Total extinction: pot stays in escrow and carries to the next event.
        event.conclude(winner_id)
        await self.repo.save_event(event)

        if self.game:
            self.game.end(guild_id)

        return ConcludeResult(
            guild_id=guild_id,
            status=event.status,
            winner_id=winner_id,
            survivor_count=len(survivors),
            pot_total=pot,
            pot_formatted=event.formatted_pot,
            payout_per_survivor=payout_per,
        )

    async def get_status(self, guild_id: str) -> StatusResult:
        event = await self.repo.get_active_event(guild_id)
        if not event:
            raise EntityNotFoundError("No active event.")
        players = await self.repo.list_players(guild_id, event.event_id)
        alive = [p for p in players if p.is_alive]
        current_game = self.games[event.current_game_index].name if self.games else "None"
        return StatusResult(
            guild_id=guild_id,
            status=event.status,
            pot_amount=event.pot_amount,
            pot_formatted=event.formatted_pot,
            alive_count=len(alive),
            eliminated_count=len(players) - len(alive),
            total_players=len(players),
            current_game=current_game,
            entry_fee=event.entry_fee,
        )

    # --- Game delegation (round 1 = RLGL) ---

    def start_game(self, guild_id: str, event_id: str) -> None:
        if self.game:
            self.game.start(guild_id, event_id, target=self.game.target)

    def set_light(self, guild_id: str, light: str, round_num: Optional[int] = None) -> None:
        if self.game:
            self.game.set_light(guild_id, light, round_num)

    def get_light(self, guild_id: str) -> str:
        return self.game.get_light(guild_id) if self.game else "NONE"

    def get_active_game(self, guild_id: str) -> Optional[dict]:
        return self.game.get_state(guild_id) if self.game else None

    def end_game(self, guild_id: str) -> None:
        if self.game:
            self.game.end(guild_id)

    def reset_all_games(self) -> None:
        for game in self.games:
            game.reset_all()

    async def get_active_racers(self, guild_id: str):
        return await self.game.get_active_racers(guild_id) if self.game else []

    async def handle_move(self, guild_id: str, user_id: str):
        if not self.game:
            raise ValidationError("No game module registered.")
        return await self.game.handle_move(guild_id, user_id)

    async def clear_session(self, guild_id: str) -> None:
        if self.game:
            self.game.end(guild_id)