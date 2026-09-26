import time
import unittest
from unittest.mock import AsyncMock
from src.domain.entities.squid_player import SquidPlayer
from src.domain.entities.squid_season import SquidSeason
from src.application.dtos.squid_dtos import EnrollPlayerDTO, RedLightMoveDTO
from src.application.services.squid_service import SquidService
from src.domain.errors import ValidationError

class TestSquidService(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_repo = AsyncMock()
        self.mock_synth = AsyncMock()
        self.mock_synth.synthesize.return_value = b"MOCK_GUARD_WAV"
        self.service = SquidService(self.mock_repo, self.mock_synth)

    async def test_enroll_player(self):
        self.mock_repo.get_player.return_value = None
        self.mock_repo.get_next_available_number.return_value = "001"

        dto = EnrollPlayerDTO(guild_id="111", user_id="222")
        result = await self.service.enroll_player(dto)

        self.assertEqual(result.player_number, "001")
        self.assertEqual(result.display_tag, "Player 001")
        self.mock_repo.save_player.assert_called_once()

    async def test_enroll_player_blocked_when_game_active(self):
        self.service.start_red_light_game("111")
        dto = EnrollPlayerDTO(guild_id="111", user_id="222")
        with self.assertRaises(ValidationError) as ctx:
            await self.service.enroll_player(dto)
        self.assertIn("locked", str(ctx.exception).lower())

    async def test_eliminate_player(self):
        player = SquidPlayer(guild_id="111", user_id="222", player_number="067")
        season = SquidSeason(guild_id="111", pot_amount=0)
        self.mock_repo.get_player.return_value = player
        self.mock_repo.get_season.return_value = season

        result = await self.service.eliminate_player("111", "222", "Overdue assignment")

        self.assertFalse(player.is_alive)
        self.assertEqual(result.pot_total, 100_000_000)
        self.assertEqual(result.pot_formatted, "₩ 100,000,000")
        self.assertEqual(result.audio_bytes, b"MOCK_GUARD_WAV")
        self.mock_synth.synthesize.assert_called_once()

    async def test_red_light_latency_grace(self):
        player = SquidPlayer(guild_id="111", user_id="222", player_number="456")
        self.mock_repo.get_player.return_value = player

        self.service.start_red_light_game("111", target=100)
        self.service.set_light("111", "RED")

        dto = RedLightMoveDTO(guild_id="111", user_id="222")
        result = await self.service.process_move(dto)

        # Immediate move within 0.5s survives under latency grace
        self.assertTrue(result.survived)
        self.assertIn("grace", result.status_message.lower())
        self.mock_repo.record_anomaly.assert_called_once()

    async def test_red_light_move_elimination(self):
        player = SquidPlayer(guild_id="111", user_id="222", player_number="456")
        season = SquidSeason(guild_id="111")
        self.mock_repo.get_player.return_value = player
        self.mock_repo.get_season.return_value = season

        self.service.start_red_light_game("111", target=100)
        self.service.set_light("111", "RED")
        # Simulate move arriving 1.0s after red light (exceeding 0.5s grace)
        self.service._active_games["111"]["red_light_time"] = time.monotonic() - 1.0

        dto = RedLightMoveDTO(guild_id="111", user_id="222")
        result = await self.service.process_move(dto)

        self.assertFalse(result.survived)
        self.assertIn("eliminated", result.status_message.lower())
        self.assertEqual(result.audio_bytes, b"MOCK_GUARD_WAV")
        self.mock_repo.record_anomaly.assert_called_once()

    async def test_green_light_move_advancement(self):
        player = SquidPlayer(guild_id="111", user_id="222", player_number="001")
        self.mock_repo.get_player.return_value = player

        self.service.start_red_light_game("111", target=100)
        self.service.set_light("111", "GREEN")

        dto = RedLightMoveDTO(guild_id="111", user_id="222")
        result = await self.service.process_move(dto)

        self.assertTrue(result.survived)
        self.assertGreater(result.distance, 0)

    async def test_preload_audio_cache(self):
        await self.service.preload_audio_cache()
        cached_red = self.service.get_cached_audio("red")
        cached_green = self.service.get_cached_audio("green_korean")
        self.assertEqual(cached_red, b"MOCK_GUARD_WAV")
        self.assertEqual(cached_green, b"MOCK_GUARD_WAV")

    def test_dynamic_distance_narrowing(self):
        dist_r1 = [self.service._calculate_advance(1) for _ in range(20)]
        dist_r5 = [self.service._calculate_advance(5) for _ in range(20)]
        # Round 1 has higher max than Round 5
        self.assertGreater(max(dist_r1), min(dist_r5))

    async def test_revive_all_players(self):
        self.mock_repo.revive_all_players.return_value = 5
        count = await self.service.revive_all_players("111")
        self.assertEqual(count, 5)
        self.mock_repo.revive_all_players.assert_called_once_with("111")

    async def test_timeout_slacking_players(self):
        p1 = SquidPlayer(guild_id="111", user_id="u1", player_number="001", is_alive=True)
        p2 = SquidPlayer(guild_id="111", user_id="u2", player_number="002", is_alive=True)
        season = SquidSeason(guild_id="111")
        self.mock_repo.list_players.return_value = [p1, p2]
        self.mock_repo.get_player.side_effect = lambda g, u: p1 if u == "u1" else p2
        self.mock_repo.get_season.return_value = season

        self.service.start_red_light_game("111", target=100)
        # u1 finished (100m), u2 slacked (40m)
        self.service._active_games["111"]["finished"].add("u1")
        self.service._active_games["111"]["progress"]["u1"] = 100
        self.service._active_games["111"]["progress"]["u2"] = 40

        elims = await self.service.timeout_slacking_players("111")
        self.assertEqual(len(elims), 1)
        self.assertEqual(elims[0].user_id, "u2")
        self.assertIn("Failed to reach the finish line", elims[0].reason)

    async def test_get_active_racers(self):
        p1 = SquidPlayer(guild_id="111", user_id="u1", player_number="001", is_alive=True)
        p2 = SquidPlayer(guild_id="111", user_id="u2", player_number="002", is_alive=True)
        self.mock_repo.list_players.return_value = [p1, p2]

        self.service.start_red_light_game("111", target=100)
        # Initially both are active racers
        racers = await self.service.get_active_racers("111")
        self.assertEqual(len(racers), 2)

        # u1 crosses finish line
        self.service._active_games["111"]["finished"].add("u1")
        racers = await self.service.get_active_racers("111")
        self.assertEqual(len(racers), 1)
        self.assertEqual(racers[0].user_id, "u2")

        # u2 crosses finish line
        self.service._active_games["111"]["finished"].add("u2")
        racers = await self.service.get_active_racers("111")
        self.assertEqual(len(racers), 0)

    async def test_clear_session(self):
        self.service.start_red_light_game("111", target=100)
        self.assertIn("111", self.service._active_games)

        await self.service.clear_session("111")
        self.assertNotIn("111", self.service._active_games)
        self.mock_repo.clear_players.assert_called_once_with("111")

if __name__ == "__main__":
    unittest.main()
