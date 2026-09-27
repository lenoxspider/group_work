"""Integration tests for SQLiteGamesRepository."""

import os
import tempfile
import unittest

from src.infrastructure.database.connection import DatabaseManager
from src.plugins.games.domain import CONCLUDED, REGISTERING, Event, Player, Vote, utcnow
from src.plugins.games.repository import SQLiteGamesRepository
from src.plugins.games.schema import GAMES_SCHEMA


class TestSQLiteGamesRepository(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.temp_file.close()
        self.db_manager = DatabaseManager(self.temp_file.name)
        self.db_manager.register_plugin_schema("games", GAMES_SCHEMA)
        await self.db_manager.initialize_schema()
        self.repo = SQLiteGamesRepository(self.temp_file.name)

    async def asyncTearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    async def test_event_save_and_get(self):
        event = Event(event_id="EV-1", guild_id="g1", status=REGISTERING, entry_fee=100)
        await self.repo.save_event(event)
        got = await self.repo.get_event("EV-1")
        self.assertEqual(got.event_id, "EV-1")
        self.assertEqual(got.entry_fee, 100)
        self.assertEqual(got.status, REGISTERING)

    async def test_get_active_event_returns_none_after_conclude(self):
        await self.repo.save_event(Event(event_id="EV-1", guild_id="g1", status=REGISTERING))
        active = await self.repo.get_active_event("g1")
        self.assertEqual(active.event_id, "EV-1")

        await self.repo.save_event(Event(event_id="EV-1", guild_id="g1", status=CONCLUDED, winner_id="u1"))
        self.assertIsNone(await self.repo.get_active_event("g1"))

    async def test_player_save_get_list(self):
        p1 = Player(guild_id="g1", event_id="EV-1", user_id="u1", player_number="001")
        p2 = Player(
            guild_id="g1", event_id="EV-1", user_id="u2", player_number="002",
            is_alive=False, elimination_reason="moved",
        )
        await self.repo.save_player(p1)
        await self.repo.save_player(p2)

        got = await self.repo.get_player("g1", "EV-1", "u1")
        self.assertEqual(got.display_tag, "Player 001")
        self.assertTrue(got.is_alive)

        all_players = await self.repo.list_players("g1", "EV-1")
        self.assertEqual(len(all_players), 2)
        alive = await self.repo.list_players("g1", "EV-1", alive_only=True)
        self.assertEqual(len(alive), 1)
        self.assertEqual(alive[0].user_id, "u1")

    async def test_get_next_number_sequential(self):
        self.assertEqual(await self.repo.get_next_number("g1", "EV-1"), "001")
        await self.repo.save_player(Player(guild_id="g1", event_id="EV-1", user_id="u1", player_number="001"))
        self.assertEqual(await self.repo.get_next_number("g1", "EV-1"), "002")

    async def test_vote_record_and_list(self):
        await self.repo.record_vote(Vote(guild_id="g1", event_id="EV-1", user_id="u1", choice="stop", voted_at=utcnow()))
        votes = await self.repo.list_votes("g1", "EV-1")
        self.assertEqual(len(votes), 1)
        self.assertEqual(votes[0].choice, "stop")
        self.assertEqual(votes[0].user_id, "u1")