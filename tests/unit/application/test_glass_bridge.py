"""Unit tests for the Glass Bridge game module.

The mechanics that must be exactly right:
- turn order is the join order, and order[0] is always the current player
- a player keeps stepping until they fall or cross
- a panel someone dies on is revealed to everyone behind them
- the crossing ends only when every player has fallen or crossed
"""

import random
import unittest

from src.plugins.games.glass_bridge import (
    CROSSED,
    FELL,
    STEPPED_SAFE,
    STALLED,
    GlassBridge,
    NoActiveBridge,
    NotYourTurn,
)

GUILD = "g1"
P1, P2, P3 = "u1", "u2", "u3"


class TestGlassBridge(unittest.TestCase):
    def _game(self, rows=4, players=(P1, P2, P3), seed=7):
        game = GlassBridge(rng=random.Random(seed))
        game.start(GUILD, "e1", list(players), rows=rows)
        return game

    def _safe(self, game):
        return game.get_state(GUILD)["safe"]

    def _pick(self, game, correct=True, row=None):
        """The correct or wrong side for the current row."""
        row = game.get_state(GUILD)["current_row"] if row is None else row
        safe = self._safe(game)[row]
        if correct:
            return safe
        return "left" if safe == "right" else "right"

    # --- setup and guards ---

    def test_empty_players_is_rejected(self):
        with self.assertRaises(ValueError):
            GlassBridge().start(GUILD, "e1", [])

    def test_no_bridge_rejects_a_move(self):
        game = GlassBridge(rng=random.Random(1))
        with self.assertRaises(NoActiveBridge):
            game.handle_choice(GUILD, P1, "left")

    def test_invalid_side_rejected(self):
        game = self._game()
        with self.assertRaises(ValueError):
            game.handle_choice(GUILD, P1, "up")

    def test_out_of_turn_is_rejected(self):
        game = self._game()
        self.assertEqual(game.current_player(GUILD), P1)
        with self.assertRaises(NotYourTurn):
            game.handle_choice(GUILD, P2, self._pick(game))

    # --- stepping ---

    def test_a_safe_step_keeps_the_same_player(self):
        game = self._game()
        move = game.handle_choice(GUILD, P1, self._pick(game))
        self.assertEqual(move.outcome, STEPPED_SAFE)
        self.assertEqual(game.current_player(GUILD), P1, "a safe step does not pass the turn")
        self.assertFalse(move.bridge_done)

    def test_a_fall_passes_to_the_next_player(self):
        game = self._game()
        move = game.handle_choice(GUILD, P1, self._pick(game, correct=False))
        self.assertEqual(move.outcome, FELL)
        self.assertEqual(move.current_player, P2)
        self.assertIn(P1, game.get_state(GUILD)["fell"])

    def test_the_cruel_mechanic_the_panel_someone_died_on_is_known(self):
        game = self._game()
        game.handle_choice(GUILD, P1, self._pick(game, correct=False))
        known = game.get_state(GUILD)["known"]
        self.assertIsNotNone(known[0], "the row P1 died on must now be known")
        self.assertEqual(known[0], self._safe(game)[0])

    def test_a_later_player_steps_through_what_was_proven(self):
        """P1 dies on row 0; P2 steps onto the known-safe panel without risk."""
        game = self._game()
        game.handle_choice(GUILD, P1, self._pick(game, correct=False))
        safe_row0 = self._safe(game)[0]
        move = game.handle_choice(GUILD, P2, safe_row0)
        self.assertEqual(move.outcome, STEPPED_SAFE)
        self.assertEqual(move.current_player, P2)

    # --- crossing and completion ---

    def test_crossing_the_final_row_resolves_that_player(self):
        game = self._game(rows=2)
        game.handle_choice(GUILD, P1, self._pick(game, row=0))
        move = game.handle_choice(GUILD, P1, self._pick(game, row=1))
        self.assertEqual(move.outcome, CROSSED)
        self.assertIn(P1, game.get_state(GUILD)["crossed"])
        self.assertEqual(move.current_player, P2, "the next player crosses after one finishes")
        self.assertFalse(move.bridge_done, "others still need to cross")

    def test_row_position_resets_for_the_next_player(self):
        game = self._game(rows=3)
        game.handle_choice(GUILD, P1, self._pick(game, row=0))
        game.handle_choice(GUILD, P1, self._pick(game, row=1))
        game.handle_choice(GUILD, P1, self._pick(game, correct=False, row=2))
        self.assertEqual(game.get_state(GUILD)["current_row"], 0, "P2 starts from the near side")

    def test_the_crossing_ends_only_when_everyone_has_resolved(self):
        game = self._game(rows=1, players=(P1, P2, P3))
        # P1 crosses, P2 falls, P3 crosses
        game.handle_choice(GUILD, P1, self._pick(game))
        self.assertFalse(game.get_state(GUILD)["done"])
        game.handle_choice(GUILD, P2, self._pick(game, correct=False))
        self.assertFalse(game.get_state(GUILD)["done"])
        move = game.handle_choice(GUILD, P3, self._pick(game))
        self.assertTrue(move.bridge_done)
        self.assertTrue(game.get_state(GUILD)["done"])

    def test_no_move_is_possible_after_the_bridge_ends(self):
        game = self._game(rows=1, players=(P1,))
        game.handle_choice(GUILD, P1, self._pick(game))
        with self.assertRaises(NoActiveBridge):
            game.handle_choice(GUILD, P1, self._pick(game))

    # --- stalling ---

    def test_stalling_eliminates_the_current_player(self):
        game = self._game()
        move = game.handle_stall(GUILD)
        self.assertEqual(move.outcome, STALLED)
        self.assertEqual(move.user_id, P1)
        self.assertEqual(move.current_player, P2)
        self.assertIn(P1, game.get_state(GUILD)["fell"])

    def test_stalling_does_not_reveal_the_row(self):
        """A stall is not a step - the panels stay unknown for the next player."""
        game = self._game()
        game.handle_stall(GUILD)
        self.assertIsNone(game.get_state(GUILD)["known"][0])

    def test_stall_on_a_finished_bridge_is_a_noop(self):
        game = self._game(rows=1, players=(P1,))
        game.handle_choice(GUILD, P1, self._pick(game))
        self.assertIsNone(game.handle_stall(GUILD))

    # --- board snapshot ---

    def test_board_snapshot_reflects_the_crossing(self):
        game = self._game(rows=2)
        game.handle_choice(GUILD, P1, self._pick(game, correct=False))
        board = game.board(GUILD)
        self.assertEqual(board["rows"], 2)
        self.assertEqual(board["queue"], [P2, P3])
        self.assertEqual(board["fell"], [P1])
        self.assertEqual(board["current_player"], P2)
        self.assertIsNotNone(board["known"][0])

    def test_end_clears_the_bridge(self):
        game = self._game()
        self.assertTrue(game.is_active(GUILD))
        game.end(GUILD)
        self.assertFalse(game.is_active(GUILD))
        self.assertIsNone(game.board(GUILD))


if __name__ == "__main__":
    unittest.main()
