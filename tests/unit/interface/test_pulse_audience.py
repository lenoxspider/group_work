"""Unit tests for the shared presence tracker and the pulse audience trigger.

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
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.interface.presence import AUDIENCE_WINDOW_MINUTES, PresenceTracker
from src.plugins.pulse.cog import PulseCog
from src.plugins.pulse.domain import PULSE_COOLDOWN_MINUTES, utcnow


def _cog(last_fired_seconds=None) -> PulseCog:
    """Build a PulseCog without __init__, which would start the task loop."""
    cog = object.__new__(PulseCog)
    cog.bot = SimpleNamespace(presence=PresenceTracker())
    service = AsyncMock()
    service.last_fired_seconds = AsyncMock(return_value=last_fired_seconds)
    cog.service = service
    return cog


def _active_minutes_ago(cog: PulseCog, guild_id: str, minutes: float) -> None:
    cog.bot.presence.note(guild_id, utcnow() - timedelta(minutes=minutes))


class TestPresenceTracker(unittest.TestCase):
    def test_no_history_is_not_an_audience(self):
        tracker = PresenceTracker()
        self.assertIsNone(tracker.minutes_since("g1"))
        self.assertFalse(tracker.audience_present("g1"))

    def test_recent_activity_is_an_audience(self):
        tracker = PresenceTracker()
        tracker.note("g1")
        self.assertTrue(tracker.audience_present("g1"))

    def test_stale_activity_is_not_an_audience(self):
        tracker = PresenceTracker()
        tracker.note("g1", utcnow() - timedelta(minutes=AUDIENCE_WINDOW_MINUTES + 1))
        self.assertFalse(tracker.audience_present("g1"))

    def test_guilds_are_tracked_separately(self):
        tracker = PresenceTracker()
        tracker.note("g1")
        self.assertTrue(tracker.audience_present("g1"))
        self.assertFalse(tracker.audience_present("g2"))

    def test_window_is_configurable(self):
        tracker = PresenceTracker(window_minutes=5)
        tracker.note("g1", utcnow() - timedelta(minutes=10))
        self.assertFalse(tracker.audience_present("g1"))


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
