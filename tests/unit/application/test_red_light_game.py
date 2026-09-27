"""Unit tests for the Red Light Green Light game module."""

import random
import unittest
from types import SimpleNamespace

from src.plugins.games.domain import Player
from src.plugins.games.red_light import RedLightGreenLight


class FakeClock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class FakeRepo:
    def __init__(self, players=None):
        self.players = players or {}
        self.anomalies = []
        self.saved = []

    async def get_player(self, guild_id, event_id, user_id):
        return self.players.get((guild_id, event_id, user_id))

    async def record_anomaly(self, guild_id, event_id, user_id, reason):
        self.anomalies.append(reason)

    async def save_player(self, player):
        self.saved.append(player)


class FakeArena:
    def __init__(self, repo):
        self.repo = repo
        self.eliminated = []

    async def eliminate_player(self, guild_id, user_id, reason, synthesize_audio=True):
        self.eliminated.append((user_id, reason))
        return SimpleNamespace(audio_bytes=None)


class TestRedLightGreenLight(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.guild = "g1"
        self.event = "e1"
        self.user = "u1"
        self.player = Player(
            guild_id=self.guild, event_id=self.event, user_id=self.user, player_number="001"
        )
        self.repo = FakeRepo(players={(self.guild, self.event, self.user): self.player})
        self.arena = FakeArena(self.repo)
        self.clock = FakeClock()
        self.game = RedLightGreenLight(self.arena, clock=self.clock, rng=random.Random(0))
        self.game.start(self.guild, self.event, target=100)

    async def test_green_move_advances(self):
        res = await self.game.handle_move(self.guild, self.user)
        self.assertTrue(res.survived)
        self.assertGreater(res.distance, 0)
        self.assertGreater(res.advance, 0)
        self.assertEqual(res.status_code, "ok")

    async def test_double_tap_ignored(self):
        await self.game.handle_move(self.guild, self.user)
        self.clock.t += 0.1
        res = await self.game.handle_move(self.guild, self.user)
        self.assertTrue(res.is_rate_limited)
        self.assertEqual(res.status_code, "double_tap")

    async def test_red_light_grace_survives(self):
        self.game.set_light(self.guild, "RED")
        self.clock.t += 0.1
        res = await self.game.handle_move(self.guild, self.user)
        self.assertTrue(res.survived)
        self.assertEqual(res.status_code, "grace")

    async def test_red_light_move_eliminates(self):
        self.game.set_light(self.guild, "RED")
        self.clock.t += 1.0
        res = await self.game.handle_move(self.guild, self.user)
        self.assertFalse(res.survived)
        self.assertEqual(res.status_code, "eliminated")
        self.assertEqual(len(self.arena.eliminated), 1)

    async def test_sprint_limit(self):
        await self.game.handle_move(self.guild, self.user)
        self.clock.t += 1.0
        await self.game.handle_move(self.guild, self.user)
        self.clock.t += 1.0
        res = await self.game.handle_move(self.guild, self.user)
        self.assertEqual(res.status_code, "sprint_limit")

    async def test_finish_advances_survival(self):
        game = RedLightGreenLight(self.arena, clock=self.clock, rng=random.Random(0))
        game.start(self.guild, self.event, target=5)
        res = await game.handle_move(self.guild, self.user)
        self.assertTrue(res.is_finished)
        self.assertEqual(self.player.survival_streak, 1)