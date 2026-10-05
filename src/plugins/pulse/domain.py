"""Pulse domain - the shape of a live pulse and its pacing constants."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Pacing (minutes / seconds)
PULSE_COOLDOWN_MINUTES = 120   # never fire more often than this
SILENCE_MINUTES = 30           # only fire when the hall has gone quiet this long
PULSE_TIMEOUT_SECONDS = 90     # default: how long a reflex/riddle pulse stays open
PULSE_PRIZE_SPI = 100          # reward for a reflex/riddle win

# Snap Trial (vote mode)
SNAP_TIMEOUT_SECONDS = 300     # 5-minute jury window
SNAP_FINE_SPI = 50             # guilty: paid to the treasury
SNAP_COMPENSATION_SPI = 25     # innocent: the collective pays the accused
SNAP_GUILTY_EMOJI = "✅"
SNAP_INNOCENT_EMOJI = "❌"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class ActivePulse:
    guild_id: str
    channel_id: str
    message_id: str
    kind: str
    label: str
    answer: str
    mode: str
    started_at: datetime
    accept: tuple = ()
    vote_options: dict = field(default_factory=dict)
    timeout_seconds: int = PULSE_TIMEOUT_SECONDS
    data: dict = field(default_factory=dict)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or utcnow()
        return (now - self.started_at).total_seconds() > self.timeout_seconds
