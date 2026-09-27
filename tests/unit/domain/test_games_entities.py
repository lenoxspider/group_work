"""Unit tests for games domain entities and guard voice lines."""

import unittest

from datetime import datetime

from src.domain.errors import ValidationError
from src.plugins.games.domain import (
    CONCLUDED,
    ONGOING,
    REGISTERING,
    Event,
    GuardVoiceLines,
    Player,
    Vote,
)


class TestEvent(unittest.TestCase):
    def test_defaults(self):
        event = Event(event_id="EV-1", guild_id="g1")
        self.assertEqual(event.status, REGISTERING)
        self.assertEqual(event.pot_amount, 0)
        self.assertEqual(event.entry_fee, 100)
        self.assertEqual(event.formatted_pot, "0 spi")

    def test_formatted_pot(self):
        event = Event(event_id="EV-1", guild_id="g1", pot_amount=1234567)
        self.assertEqual(event.formatted_pot, "1,234,567 spi")

    def test_begin(self):
        event = Event(event_id="EV-1", guild_id="g1")
        event.begin()
        self.assertEqual(event.status, ONGOING)
        self.assertIsNotNone(event.started_at)

    def test_conclude(self):
        event = Event(event_id="EV-1", guild_id="g1")
        event.conclude("u1")
        self.assertEqual(event.status, CONCLUDED)
        self.assertEqual(event.winner_id, "u1")
        self.assertIsNotNone(event.concluded_at)


class TestPlayer(unittest.TestCase):
    def test_display_tag_and_spoken_number(self):
        player = Player(guild_id="g", event_id="e", user_id="u", player_number="067")
        self.assertEqual(player.display_tag, "Player 067")
        self.assertEqual(player.spoken_number, "zero six seven")

    def test_invalid_player_number(self):
        with self.assertRaises(ValidationError):
            Player(guild_id="g", event_id="e", user_id="u", player_number="67")
        with self.assertRaises(ValidationError):
            Player(guild_id="g", event_id="e", user_id="u", player_number="ABC")

    def test_eliminate(self):
        player = Player(guild_id="g", event_id="e", user_id="u", player_number="001")
        player.eliminate("moved on red")
        self.assertFalse(player.is_alive)
        self.assertEqual(player.elimination_reason, "moved on red")
        self.assertIsNotNone(player.eliminated_at)

    def test_advance_survival(self):
        player = Player(guild_id="g", event_id="e", user_id="u", player_number="001")
        player.advance_survival()
        self.assertEqual(player.survival_streak, 1)

    def test_advance_survival_on_dead_raises(self):
        player = Player(guild_id="g", event_id="e", user_id="u", player_number="001")
        player.eliminate("x")
        with self.assertRaises(ValidationError):
            player.advance_survival()


class TestVote(unittest.TestCase):
    def test_vote_fields(self):
        vote = Vote(guild_id="g", event_id="e", user_id="u", choice="stop", voted_at=datetime.now())
        self.assertEqual(vote.choice, "stop")
        self.assertEqual(vote.user_id, "u")


class TestGuardVoiceLines(unittest.TestCase):
    def test_elimination_line(self):
        self.assertEqual(
            GuardVoiceLines.elimination("zero six seven"),
            "Player zero six seven. Eliminated.",
        )

    def test_red_light_line(self):
        self.assertEqual(GuardVoiceLines.red_light(), "Red light. Remain still.")