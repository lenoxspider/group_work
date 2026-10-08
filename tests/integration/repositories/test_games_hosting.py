"""Integration tests for bot-hosted arena rounds.

The specific failure these guard against: an event left sitting in REGISTERING
stays in ACTIVE_STATUSES forever, and open_event() refuses to create another
one - so a single hosted round that nobody joined would wedge the arena until
an admin noticed.
"""

import os
import tempfile
import unittest
from datetime import timedelta

import aiosqlite

from src.plugins.games.domain import (
    ACTIVE_STATUSES,
    CANCELLED,
    HOSTED_ENTRY_FEE,
    ONGOING,
    REGISTERING,
    Event,
    utcnow,
)
from src.plugins.games.repository import SQLiteGamesRepository
from src.plugins.games.schema import GAMES_SCHEMA
from src.plugins.games.service import ArenaService

GUILD = "guild-hosting"


class TestArenaHosting(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        async with aiosqlite.connect(self.db_path) as db:
            for stmt in GAMES_SCHEMA:
                await db.execute(stmt)
            await db.commit()
        self.repo = SQLiteGamesRepository(self.db_path)
        self.arena = ArenaService(self.repo, None)

    async def asyncTearDown(self):
        os.remove(self.db_path)

    async def test_opened_at_is_recorded_and_survives_a_round_trip(self):
        event = await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        self.assertIsNotNone(event.opened_at)
        reloaded = await self.repo.get_event(event.event_id)
        self.assertIsNotNone(reloaded.opened_at)
        self.assertEqual(reloaded.status, REGISTERING)

    async def test_hosted_round_is_free_to_enter(self):
        event = await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        self.assertEqual(event.entry_fee, 0)

    async def test_empty_registration_can_be_cancelled(self):
        event = await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        cancelled = await self.arena.cancel_event(GUILD)
        self.assertIsNotNone(cancelled)
        self.assertEqual(cancelled.status, CANCELLED)
        self.assertEqual(cancelled.event_id, event.event_id)

    async def test_cancelled_event_no_longer_blocks_the_arena(self):
        """The wedge: without cancellation, this second open would raise."""
        await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        await self.arena.cancel_event(GUILD)
        self.assertIsNone(await self.arena.get_active_event(GUILD))
        second = await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        self.assertEqual(second.status, REGISTERING)

    async def test_cancel_is_not_an_active_status(self):
        self.assertNotIn(CANCELLED, ACTIVE_STATUSES)

    async def test_cancel_refuses_to_touch_a_game_underway(self):
        event = await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        event.status = ONGOING
        await self.repo.save_event(event)
        self.assertIsNone(await self.arena.cancel_event(GUILD))
        still = await self.repo.get_event(event.event_id)
        self.assertEqual(still.status, ONGOING)

    async def test_cancel_with_no_event_is_a_noop(self):
        self.assertIsNone(await self.arena.cancel_event(GUILD))

    async def test_seconds_since_last_event_is_none_when_never_hosted(self):
        self.assertIsNone(await self.arena.seconds_since_last_event(GUILD))

    async def test_seconds_since_last_event_measures_a_fresh_round(self):
        await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        secs = await self.arena.seconds_since_last_event(GUILD)
        self.assertIsNotNone(secs)
        self.assertLess(secs, 60)

    async def test_cooldown_sees_cancelled_rounds_too(self):
        """A restart must not let the bot host again straight after a cancel."""
        await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        await self.arena.cancel_event(GUILD)
        secs = await self.arena.seconds_since_last_event(GUILD)
        self.assertIsNotNone(secs)
        self.assertLess(secs, 60)

    async def test_registration_player_count_starts_at_zero(self):
        event = await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        self.assertEqual(await self.arena.registration_player_count(GUILD, event.event_id), 0)

    async def test_stale_registration_is_identifiable_by_age(self):
        event = await self.arena.open_event(GUILD, HOSTED_ENTRY_FEE)
        event.opened_at = utcnow() - timedelta(minutes=45)
        await self.repo.save_event(event)
        reloaded = await self.repo.get_active_event(GUILD)
        age = (utcnow() - reloaded.opened_at).total_seconds() / 60.0
        self.assertGreater(age, 30)

    async def test_legacy_event_without_opened_at_is_skipped_not_crashed(self):
        """Rows written before the migration have no opened_at."""
        legacy = Event(event_id="EV-LEGACY01", guild_id=GUILD, status=REGISTERING)
        await self.repo.save_event(legacy)
        reloaded = await self.repo.get_active_event(GUILD)
        self.assertIsNone(reloaded.opened_at)


if __name__ == "__main__":
    unittest.main()
