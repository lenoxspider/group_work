"""Unit tests for the pulse audience trigger.

The pulse used to fire when the hall went *quiet*, on the theory that silence
meant people lurking who needed a nudge. In practice it fired into an empty
room at 03:00, and fired on the first loop tick after every restart because no
activity had been recorded yet - so `_last_activity` was empty and the old
"not recent activity" check passed vacuously.

These pin the replacement rule: a pulse only fires when someone has been active
recently enough to actually see it land.
"""

import unittest
from datetime import timedelta
from unittest.mock import AsyncMock

from src.plugins.pulse.cog import PulseCog
from src.plugins.pulse.domain import AUDIENCE_WINDOW_MINUTES, PULSE_COOLDOWN_MINUTES, utcnow


def _cog(last_fired_seconds=None) -> PulseCog:
    """Build a PulseCog without __init__, which would start the task loop."""
    cog = object.__new__(PulseCog)
    cog._last_activity = {}
    service = AsyncMock()
    service.last_fired_seconds = AsyncMock(return_value=last_fired_seconds)
    cog.service = service
    return cog


def _active_minutes_ago(cog: PulseCog, guild_id: str, minutes: float) -> None:
    cog._last_activity[guild_id] = utcnow() - timedelta(minutes=minutes)


class TestPulseAudienceTrigger(unittest.IsolatedAsyncioTestCase):
    async def test_never_fires_when_no_activity_has_ever_been_seen(self):
        """Regression: the old rule fired here, treating 'unknown' as 'quiet'."""
        cog = _cog()
        self.assertFalse(cog._audience_present("g1"))
        self.assertFalse(await cog._should_fire("g1"))

    async def test_fires_when_someone_was_just_active(self):
        cog = _cog()
        _active_minutes_ago(cog, "g1", 2)
        self.assertTrue(cog._audience_present("g1"))
        self.assertTrue(await cog._should_fire("g1"))

    async def test_does_not_fire_into_a_long_silence(self):
        cog = _cog()
        _active_minutes_ago(cog, "g1", AUDIENCE_WINDOW_MINUTES + 15)
        self.assertFalse(cog._audience_present("g1"))
        self.assertFalse(await cog._should_fire("g1"))

    async def test_activity_just_inside_the_window_still_counts(self):
        cog = _cog()
        _active_minutes_ago(cog, "g1", AUDIENCE_WINDOW_MINUTES - 1)
        self.assertTrue(cog._audience_present("g1"))

    async def test_cooldown_beats_a_present_audience(self):
        cog = _cog(last_fired_seconds=(PULSE_COOLDOWN_MINUTES - 5) * 60)
        _active_minutes_ago(cog, "g1", 0)
        self.assertTrue(cog._audience_present("g1"))
        self.assertFalse(await cog._should_fire("g1"))

    async def test_fires_once_the_cooldown_has_elapsed(self):
        cog = _cog(last_fired_seconds=(PULSE_COOLDOWN_MINUTES + 1) * 60)
        _active_minutes_ago(cog, "g1", 1)
        self.assertTrue(await cog._should_fire("g1"))

    async def test_activity_is_tracked_per_guild(self):
        cog = _cog()
        _active_minutes_ago(cog, "g1", 0)
        self.assertTrue(cog._audience_present("g1"))
        self.assertFalse(cog._audience_present("g2"))

    async def test_minutes_since_activity_is_none_without_history(self):
        cog = _cog()
        self.assertIsNone(cog._minutes_since_activity("g1"))


if __name__ == "__main__":
    unittest.main()
