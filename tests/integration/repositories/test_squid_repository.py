"""Integration tests for SquidSqliteRepository."""

import os
import tempfile
import unittest
from datetime import datetime

from src.domain.entities.squid_player import SquidPlayer
from src.domain.entities.squid_season import SquidSeason
from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.database.squid_sqlite_repo import SquidSqliteRepository

class TestSquidSqliteRepository(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        self.db_manager = DatabaseManager(self.db_path)
        await self.db_manager.initialize_schema()
        self.repo = SquidSqliteRepository(self.db_path)

    async def asyncTearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    async def test_save_and_get_player(self):
        player = SquidPlayer(
            guild_id="guild_1",
            user_id="user_1",
            player_number="067",
            is_alive=True,
            survival_streak=2
        )
        await self.repo.save_player(player)

        fetched = await self.repo.get_player("guild_1", "user_1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.player_number, "067")
        self.assertEqual(fetched.survival_streak, 2)
        self.assertTrue(fetched.is_alive)

    async def test_get_next_available_number(self):
        n1 = await self.repo.get_next_available_number("guild_1")
        self.assertEqual(n1, "001")

        p1 = SquidPlayer(guild_id="guild_1", user_id="u1", player_number="001")
        await self.repo.save_player(p1)

        n2 = await self.repo.get_next_available_number("guild_1")
        self.assertEqual(n2, "002")

    async def test_list_players_filter(self):
        p1 = SquidPlayer(guild_id="guild_1", user_id="u1", player_number="001", is_alive=True)
        p2 = SquidPlayer(guild_id="guild_1", user_id="u2", player_number="002", is_alive=False)
        await self.repo.save_player(p1)
        await self.repo.save_player(p2)

        all_players = await self.repo.list_players("guild_1")
        self.assertEqual(len(all_players), 2)

        alive_only = await self.repo.list_players("guild_1", alive_only=True)
        self.assertEqual(len(alive_only), 1)
        self.assertEqual(alive_only[0].user_id, "u1")

    async def test_save_and_get_season(self):
        season = SquidSeason(guild_id="guild_1", pot_amount=200_000_000)
        await self.repo.save_season(season)

        fetched = await self.repo.get_season("guild_1")
        self.assertIsNotNone(fetched)
        self.assertEqual(fetched.pot_amount, 200_000_000)
        self.assertEqual(fetched.formatted_pot, "₩ 200,000,000")

if __name__ == "__main__":
    unittest.main()
