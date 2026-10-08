"""Shared presence tracking - is there an audience in this guild right now?

Bot-initiated moments (the pulse, hosted arena rounds) are worthless if they
fire into an empty room, and actively harmful: an unclaimed pulse trains people
to ignore the channel it lives in. Every such feature asks this tracker the same
question before it acts, and one listener feeds it.

Deliberately in-memory. Losing the record on restart is the correct behaviour -
the bot should wait for fresh proof that someone is around rather than act on a
stale timestamp from before it rebooted.
"""

from datetime import datetime, timezone
from typing import Dict, Optional

# How recently someone must have been active to count as an audience.
AUDIENCE_WINDOW_MINUTES = 25


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PresenceTracker:
    """Records the last human activity seen per guild."""

    def __init__(self, window_minutes: int = AUDIENCE_WINDOW_MINUTES):
        self.window_minutes = window_minutes
        self._last: Dict[str, datetime] = {}

    def note(self, guild_id, when: Optional[datetime] = None) -> None:
        """Record that a human was present in this guild."""
        self._last[str(guild_id)] = when or _utcnow()

    def minutes_since(self, guild_id) -> Optional[float]:
        """Minutes since the last activity, or None if none has been seen."""
        last = self._last.get(str(guild_id))
        if last is None:
            return None
        return (_utcnow() - last).total_seconds() / 60.0

    def audience_present(self, guild_id) -> bool:
        mins = self.minutes_since(guild_id)
        return mins is not None and mins <= self.window_minutes
