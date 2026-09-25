"""
Squid Game player aggregate entity.

What it does:
- Represents an enrolled student in the Squid Game accountability system.
- Enforces player state transitions (enrollment, survival streaks, elimination).
- Formats player numbers for text display and spoken TTS pronunciation.

What it does NOT do:
- Does NOT perform database I/O or Discord messaging.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from src.domain.errors import ValidationError

DIGIT_WORDS = {
    "0": "zero",
    "1": "one",
    "2": "two",
    "3": "three",
    "4": "four",
    "5": "five",
    "6": "six",
    "7": "seven",
    "8": "eight",
    "9": "nine",
}

@dataclass
class SquidPlayer:
    """Represents a member participant in the Squid Game accountability system."""
    guild_id: str
    user_id: str
    player_number: str
    is_alive: bool = True
    survival_streak: int = 0
    elimination_reason: Optional[str] = None
    eliminated_at: Optional[datetime] = None

    def __post_init__(self) -> None:
        if not self.player_number.isdigit() or len(self.player_number) != 3:
            raise ValidationError(f"Player number must be a 3-digit string (e.g. '067'), got '{self.player_number}'")

    @property
    def display_tag(self) -> str:
        """Formatted tag e.g. 'Player 067'."""
        return f"Player {self.player_number}"

    @property
    def spoken_number(self) -> str:
        """Spoken digit-by-digit format for speech synthesis (e.g. 'zero six seven')."""
        return " ".join(DIGIT_WORDS.get(d, d) for d in self.player_number)

    def eliminate(self, reason: str, timestamp: Optional[datetime] = None) -> None:
        """Marks player as eliminated with reason and timestamp."""
        if not self.is_alive:
            return
        self.is_alive = False
        self.elimination_reason = reason
        self.eliminated_at = timestamp or datetime.now()

    def advance_survival(self) -> None:
        """Increments player's game survival streak."""
        if not self.is_alive:
            raise ValidationError("Cannot increment survival streak for an eliminated player.")
        self.survival_streak += 1
