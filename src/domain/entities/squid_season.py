"""
Squid Game season aggregate entity.

What it does:
- Manages the server's running Squid Game season and prize pot.
- Tracks pot accumulation per elimination and active season status.

What it does NOT do:
- Does NOT interact with databases or audio playback.
"""

from dataclasses import dataclass
from src.domain.errors import ValidationError

DEFAULT_POT_PER_ELIMINATION = 100_000_000

@dataclass
class SquidSeason:
    """Represents a competitive accountability season and piggy-bank prize pool."""
    guild_id: str
    pot_amount: int = 0
    is_active: bool = True
    current_game: str = "Red Light Green Light"

    @property
    def formatted_pot(self) -> str:
        """Returns formatted prize pool with Korean Won currency symbol."""
        return f"₩ {self.pot_amount:,}"

    def record_elimination_bounty(self, amount: int = DEFAULT_POT_PER_ELIMINATION) -> None:
        """Adds bounty to the prize piggy bank when a player is eliminated."""
        if amount < 0:
            raise ValidationError("Bounty amount cannot be negative.")
        self.pot_amount += amount

    def end_season(self) -> None:
        """Marks the current season as finished."""
        self.is_active = False
