"""Unit tests for the arena registration sweep.

The wedge these guard against: an event left in REGISTERING stays in
ACTIVE_STATUSES forever, and open_event() refuses to create another one. So
every registration has to be resolved - started if anyone joined, cancelled if
nobody did. A registration with players that nobody ever started is the case
that used to have no exit at all.
"""

import unittest
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.plugins.games.cog import GamesCog
from src.plugins.games.domain import (
    AUTO_START_AFTER_MINUTES,
    ONGOING,
    REGISTERING,
    REGISTRATION_TTL_MINUTES,
    Event,
    utcnow,
)

GUILD_ID = "guild-sweep"


def _event(status=REGISTERING, opened_minutes_ago=0.0) -> Event:
    ev = Event(event_id="EV-TEST0001", guild_id=GUILD_ID, status=status)
    if opened_minutes_ago is not None:
        ev.opened_at = utcnow() - timedelta(minutes=opened_minutes_ago)
    return ev


class FakeArena:
    def __init__(self, event, players=0):
        self.event = event
        self.players = players
        self.cancel_calls = 0

    async def get_active_event(self, guild_id):
        return self.event

    async def registration_player_count(self, guild_id, event_id):
        return self.players

    async def cancel_event(self, guild_id):
        self.cancel_calls += 1
        if self.event:
            self.event.cancel()
        return self.event


def _cog(arena) -> GamesCog:
    """Build a GamesCog without __init__, which would construct the runner."""
    cog = object.__new__(GamesCog)
    cog.arena = arena
    cog.bot = SimpleNamespace(guilds=[])
    cog._begin_round = AsyncMock()
    cog._game_hub = AsyncMock(return_value=None)
    return cog


def _guild():
    return SimpleNamespace(id=GUILD_ID)


class TestRegistrationSweep(unittest.IsolatedAsyncioTestCase):
    async def test_no_event_does_nothing(self):
        cog = _cog(FakeArena(None))
        await cog._resolve_registration(_guild())
        cog._begin_round.assert_not_awaited()
        self.assertEqual(cog.arena.cancel_calls, 0)

    async def test_fresh_empty_registration_is_left_open(self):
        cog = _cog(FakeArena(_event(opened_minutes_ago=5), players=0))
        await cog._resolve_registration(_guild())
        cog._begin_round.assert_not_awaited()
        self.assertEqual(cog.arena.cancel_calls, 0)

    async def test_stale_empty_registration_is_cancelled(self):
        arena = FakeArena(_event(opened_minutes_ago=REGISTRATION_TTL_MINUTES + 5), players=0)
        cog = _cog(arena)
        await cog._resolve_registration(_guild())
        self.assertEqual(arena.cancel_calls, 1)
        cog._begin_round.assert_not_awaited()

    async def test_registration_with_players_is_not_started_too_soon(self):
        cog = _cog(FakeArena(_event(opened_minutes_ago=AUTO_START_AFTER_MINUTES - 5), players=2))
        await cog._resolve_registration(_guild())
        cog._begin_round.assert_not_awaited()
        self.assertEqual(cog.arena.cancel_calls, 0)

    async def test_registration_with_players_auto_starts(self):
        cog = _cog(FakeArena(_event(opened_minutes_ago=AUTO_START_AFTER_MINUTES + 2), players=2))
        await cog._resolve_registration(_guild())
        cog._begin_round.assert_awaited_once()

    async def test_wedge_case_one_player_and_nobody_pressed_start(self):
        """Previously this sat in REGISTERING forever and blocked the arena."""
        arena = FakeArena(_event(opened_minutes_ago=REGISTRATION_TTL_MINUTES * 3), players=1)
        cog = _cog(arena)
        await cog._resolve_registration(_guild())
        cog._begin_round.assert_awaited_once()
        self.assertEqual(arena.cancel_calls, 0)

    async def test_legacy_event_without_opened_at_is_skipped(self):
        arena = FakeArena(_event(opened_minutes_ago=None), players=0)
        cog = _cog(arena)
        await cog._resolve_registration(_guild())
        cog._begin_round.assert_not_awaited()
        self.assertEqual(arena.cancel_calls, 0)

    async def test_ongoing_game_is_left_alone(self):
        arena = FakeArena(_event(status=ONGOING, opened_minutes_ago=120), players=3)
        cog = _cog(arena)
        await cog._resolve_registration(_guild())
        cog._begin_round.assert_not_awaited()
        self.assertEqual(arena.cancel_calls, 0)

    async def test_sweep_survives_a_failure_in_one_guild(self):
        arena = FakeArena(_event(opened_minutes_ago=999), players=0)
        arena.cancel_event = AsyncMock(side_effect=RuntimeError("database is locked"))
        cog = _cog(arena)
        cog.bot = SimpleNamespace(guilds=[SimpleNamespace(id="g1"), SimpleNamespace(id="g2")])
        await cog.registration_sweep()  # must not raise out of the loop


if __name__ == "__main__":
    unittest.main()
