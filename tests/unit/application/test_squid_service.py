"""Unit tests for SquidService application orchestration."""

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

    async def test_red_light_move_elimination(self):
        player = SquidPlayer(guild_id="111", user_id="222", player_number="456")
        season = SquidSeason(guild_id="111")
        self.mock_repo.get_player.return_value = player
        self.mock_repo.get_season.return_value = season

        self.service.start_red_light_game("111", target=100)
        self.service.set_light("111", "RED")

        dto = RedLightMoveDTO(guild_id="111", user_id="222")
        result = await self.service.process_move(dto)

        self.assertFalse(result.survived)
        self.assertIn("eliminated", result.status_message.lower())
        self.assertEqual(result.audio_bytes, b"MOCK_GUARD_WAV")

    async def test_green_light_move_advancement(self):
        player = SquidPlayer(guild_id="111", user_id="222", player_number="001")
        self.mock_repo.get_player.return_value = player

        self.service.start_red_light_game("111", target=100)
        self.service.set_light("111", "GREEN")

        dto = RedLightMoveDTO(guild_id="111", user_id="222")
        result = await self.service.process_move(dto)

        self.assertTrue(result.survived)
        self.assertGreater(result.distance, 0)

if __name__ == "__main__":
    unittest.main()
