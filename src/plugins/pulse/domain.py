"""Pulse domain - the shape of a live pulse and its pacing constants."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

# Pacing (minutes / seconds)
PULSE_COOLDOWN_MINUTES = 120   # never fire more often than this
SILENCE_MINUTES = 30           # only fire when the hall has gone quiet this long
PULSE_TIMEOUT_SECONDS = 90     # how long a pulse stays open
PULSE_PRIZE_SPI = 100          # reward for the winner


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

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        now = now or utcnow()
        return (now - self.started_at).total_seconds() > PULSE_TIMEOUT_SECONDS