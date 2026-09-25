"""Unit tests for Squid Game domain entities and voice presets."""

import unittest
from datetime import datetime
from src.domain.entities.squid_player import SquidPlayer
from src.domain.entities.squid_season import SquidSeason
from src.domain.entities.guard_voice import GuardVoiceLines, GUARD_PROFILE, DOLL_PROFILE
from src.domain.errors import ValidationError

class TestSquidEntities(unittest.TestCase):

    def test_player_creation_and_properties(self):
        player = SquidPlayer(
            guild_id="12345",
            user_id="67890",
            player_number="067"
        )
        self.assertEqual(player.display_tag, "Player 067")
        self.assertEqual(player.spoken_number, "zero six seven")
        self.assertTrue(player.is_alive)
        self.assertEqual(player.survival_streak, 0)

    def test_invalid_player_number_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            SquidPlayer(guild_id="12345", user_id="67890", player_number="67")  # Not 3 digits

        with self.assertRaises(ValidationError):
            SquidPlayer(guild_id="12345", user_id="67890", player_number="ABC")

    def test_player_elimination(self):
        player = SquidPlayer(guild_id="123", user_id="456", player_number="456")
        now = datetime.now()
        player.eliminate("Overdue task escalation", now)

        self.assertFalse(player.is_alive)
        self.assertEqual(player.elimination_reason, "Overdue task escalation")
        self.assertEqual(player.eliminated_at, now)

        # Incrementing survival of dead player should raise error
        with self.assertRaises(ValidationError):
            player.advance_survival()

    def test_player_advance_survival(self):
        player = SquidPlayer(guild_id="123", user_id="456", player_number="001")
        player.advance_survival()
        self.assertEqual(player.survival_streak, 1)

    def test_season_pot_accumulation(self):
        season = SquidSeason(guild_id="123")
        self.assertEqual(season.formatted_pot, "₩ 0")

        season.record_elimination_bounty(100_000_000)
        self.assertEqual(season.pot_amount, 100_000_000)
        self.assertEqual(season.formatted_pot, "₩ 100,000,000")

    def test_guard_voice_lines(self):
        line = GuardVoiceLines.elimination("zero six seven")
        self.assertEqual(line, "Player zero six seven. Eliminated.")

        self.assertEqual(GUARD_PROFILE.speed, 110)
        self.assertEqual(GUARD_PROFILE.pitch, 15)
        self.assertEqual(GUARD_PROFILE.voice_name, "en-us")

        self.assertEqual(DOLL_PROFILE.voice_name, "ko")

if __name__ == "__main__":
    unittest.main()
