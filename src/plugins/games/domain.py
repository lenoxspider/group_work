"""Games plugin domain - event, player, vote aggregates and guard voice."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from src.domain.entities.voice_profile import VoiceProfile
from src.domain.errors import ValidationError

REGISTERING = "REGISTERING"
ONGOING = "ONGOING"
VOTING = "VOTING"
CONCLUDED = "CONCLUDED"
CANCELLED = "CANCELLED"

ACTIVE_STATUSES = (REGISTERING, ONGOING, VOTING)

DEFAULT_ENTRY_FEE = 100

# Bot-hosted rounds. Entry is free because a fee would exclude exactly the
# members the round is meant to pull in - several citizens hold zero spi.
HOSTED_ENTRY_FEE = 0
REGISTRATION_TTL_MINUTES = 30   # abandon an empty registration after this long
AUTO_START_AFTER_MINUTES = 10   # begin the round this long after opening, if anyone joined
HOST_COOLDOWN_MINUTES = 720     # never host more often than once per 12h

DIGIT_WORDS = {
    "0": "zero", "1": "one", "2": "two", "3": "three", "4": "four",
    "5": "five", "6": "six", "7": "seven", "8": "eight", "9": "nine",
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class Event:
    """One run of the games. Scope for roster, pot, votes, and winner."""
    event_id: str
    guild_id: str
    status: str = REGISTERING
    pot_amount: int = 0
    current_game_index: int = 0
    entry_fee: int = DEFAULT_ENTRY_FEE
    winner_id: Optional[str] = None
    started_at: Optional[datetime] = None
    concluded_at: Optional[datetime] = None
    opened_at: Optional[datetime] = None

    @property
    def formatted_pot(self) -> str:
        return f"{self.pot_amount:,} spi"

    def begin(self) -> None:
        self.status = ONGOING
        self.started_at = self.started_at or utcnow()

    def conclude(self, winner_id: Optional[str]) -> None:
        self.status = CONCLUDED
        self.winner_id = winner_id
        self.concluded_at = utcnow()

    def cancel(self) -> None:
        """Abandon a registration that never filled.

        Without this an event opened and left alone stays in ACTIVE_STATUSES
        forever, and open_event() refuses to create another one - so a single
        empty round would wedge the arena until an admin intervened.
        """
        self.status = CANCELLED
        self.concluded_at = utcnow()


@dataclass
class Player:
    """A registered member scoped to a single event."""
    guild_id: str
    event_id: str
    user_id: str
    player_number: str
    is_alive: bool = True
    survival_streak: int = 0
    elimination_reason: Optional[str] = None
    eliminated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.player_number.isdigit() or len(self.player_number) != 3:
            raise ValidationError(
                f"Player number must be a 3-digit string (e.g. '067'), got '{self.player_number}'"
            )

    @property
    def display_tag(self) -> str:
        return f"Player {self.player_number}"

    @property
    def spoken_number(self) -> str:
        return " ".join(DIGIT_WORDS.get(d, d) for d in self.player_number)

    def eliminate(self, reason: str, timestamp: Optional[datetime] = None) -> None:
        if not self.is_alive:
            return
        self.is_alive = False
        self.elimination_reason = reason
        self.eliminated_at = timestamp or utcnow()

    def advance_survival(self) -> None:
        if not self.is_alive:
            raise ValidationError("Cannot increment survival streak for an eliminated player.")
        self.survival_streak += 1


@dataclass(frozen=True)
class Vote:
    """A single public vote cast between rounds."""
    guild_id: str
    event_id: str
    user_id: str
    choice: str  # "continue" | "stop"
    voted_at: datetime


# --- Masked guard and doll voice ---

GUARD_PROFILE = VoiceProfile(voice_name="en-us", speed=110, pitch=15, variant=None, tone="guard")
DOLL_PROFILE = VoiceProfile(voice_name="ko", speed=125, pitch=60, variant=None, tone="doll")


class GuardVoiceLines:
    """Cold guard/doll voice lines tuned for espeak-ng (-s 110 -p 15)."""

    @staticmethod
    def elimination(spoken_number: str) -> str:
        return f"Player {spoken_number}. Eliminated."

    @staticmethod
    def game_announcement(game_name: str) -> str:
        return f"Attention, players. The next game is {game_name}. Please proceed to the game area."

    @staticmethod
    def red_light() -> str:
        return "Red light. Remain still."

    @staticmethod
    def green_light_korean() -> str:
        return "무궁화 꽃이 피었습니다."

    @staticmethod
    def green_light_english() -> str:
        return "Green light. Advance now."

    @staticmethod
    def prize_update() -> str:
        return "The prize pool has been updated."