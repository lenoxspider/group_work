"""Integration tests for arena game selection and turn-game routing.

The arena used to hardcode games[0]. These pin that an event now runs the game
it was opened with, and that choices/stalls route to it - without disturbing the
RLGL path, which is games[0] and still the default.
"""

import os
import tempfile
import unittest

from src.domain.errors import ValidationError
from src.plugins.games.domain import REGISTERING
from src.plugins.games.glass_bridge import GlassBridge
from src.plugins.games.red_light import RedLightGreenLight
from src.plugins.games.repository import SQLiteGamesRepository
from src.plugins.games.schema import GAMES_SCHEMA
from src.plugins.games.service import ArenaService

GUILD = "guild-select"
REDLIGHT, BRIDGE = 0, 1


class TestArenaGameSelection(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        import aiosqlite
        async with aiosqlite.connect(self.db_path) as db:
            for stmt in GAMES_SCHEMA:
                await db.execute(stmt)
            await db.commit()
        self.repo = SQLiteGamesRepository(self.db_path)
        self.arena = ArenaService(self.repo, None)

    async def asyncTearDown(self):
        for suffix in ("", "-wal", "-shm"):
            p = self.db_path + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except OSError:
                    pass

    async def _join(self, event_id, *users):
        for u in users:
            await self.arena.join_event(GUILD, u)

    async def test_default_event_is_red_light(self):
        event = await self.arena.open_event(GUILD, entry_fee=0)
        self.assertEqual(event.current_game_index, REDLIGHT)
        game = await self.arena.current_game(GUILD)
        self.assertIsInstance(game, RedLightGreenLight)

    async def test_event_can_be_opened_as_a_bridge(self):
        event = await self.arena.open_event(GUILD, entry_fee=0, game_index=BRIDGE)
        self.assertEqual(event.current_game_index, BRIDGE)
        game = await self.arena.current_game(GUILD)
        self.assertIsInstance(game, GlassBridge)

    async def test_out_of_range_index_is_clamped(self):
        event = await self.arena.open_event(GUILD, entry_fee=0, game_index=99)
        self.assertEqual(event.current_game_index, BRIDGE, "clamped to the last game")

    async def test_starting_a_bridge_event_opens_the_crossing(self):
        await self.arena.open_event(GUILD, entry_fee=0, game_index=BRIDGE)
        await self._join(None, "u1", "u2", "u3")
        await self.arena.start_event(GUILD)
        bridge = self.arena.games[BRIDGE]
        self.assertTrue(bridge.is_active(GUILD))
        self.assertEqual(bridge.current_player(GUILD), "u1", "join order is the crossing order")

    async def test_choice_routes_to_the_bridge(self):
        await self.arena.open_event(GUILD, entry_fee=0, game_index=BRIDGE)
        await self._join(None, "u1", "u2")
        await self.arena.start_event(GUILD)
        bridge = self.arena.games[BRIDGE]
        safe = bridge.get_state(GUILD)["safe"][0]
        move = await self.arena.handle_choice(GUILD, "u1", safe)
        self.assertIn(move.outcome, ("safe", "crossed"))

    async def test_out_of_turn_choice_is_a_validation_error(self):
        await self.arena.open_event(GUILD, entry_fee=0, game_index=BRIDGE)
        await self._join(None, "u1", "u2")
        await self.arena.start_event(GUILD)
        with self.assertRaises(ValidationError):
            await self.arena.handle_choice(GUILD, "u2", "left")

    async def test_choice_with_no_game_is_a_validation_error(self):
        with self.assertRaises(ValidationError):
            await self.arena.handle_choice(GUILD, "u1", "left")

    async def test_stall_routes_to_the_bridge(self):
        await self.arena.open_event(GUILD, entry_fee=0, game_index=BRIDGE)
        await self._join(None, "u1", "u2")
        await self.arena.start_event(GUILD)
        move = await self.arena.handle_stall(GUILD)
        self.assertEqual(move.outcome, "stalled")
        self.assertEqual(move.user_id, "u1")

    async def test_conclude_ends_the_bridge_not_just_red_light(self):
        """A regression guard: conclude used to call self.game.end (games[0])."""
        await self.arena.open_event(GUILD, entry_fee=0, game_index=BRIDGE)
        await self._join(None, "u1")
        await self.arena.start_event(GUILD)
        self.assertTrue(self.arena.games[BRIDGE].is_active(GUILD))
        await self.arena.conclude_event(GUILD)
        self.assertFalse(self.arena.games[BRIDGE].is_active(GUILD))

    async def test_red_light_event_still_starts_as_before(self):
        await self.arena.open_event(GUILD, entry_fee=0)
        await self._join(None, "u1", "u2")
        event = await self.arena.start_event(GUILD)
        self.assertEqual(event.status, "ONGOING")
        self.assertTrue(self.arena.games[REDLIGHT].is_active(GUILD))
        self.assertFalse(self.arena.games[BRIDGE].is_active(GUILD))


if __name__ == "__main__":
    unittest.main()
