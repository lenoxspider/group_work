"""Unit tests for the games ArenaService (event lifecycle + economy)."""

import unittest

from src.domain.errors import ValidationError
from src.plugins.bank.domain import InsufficientFunds, POT
from src.plugins.games.domain import CONCLUDED, ONGOING, REGISTERING, Event, Player
from src.plugins.games.service import ArenaService


class InMemoryGamesRepository:
    """Minimal in-memory repo implementing the surface ArenaService needs."""

    def __init__(self):
        self.events = {}
        self.players = {}
        self.votes = []

    async def get_active_event(self, guild_id):
        for event in self.events.values():
            if event.guild_id == guild_id and event.status in (REGISTERING, ONGOING, "VOTING"):
                return event
        return None

    async def save_event(self, event):
        self.events[event.event_id] = event

    async def get_player(self, guild_id, event_id, user_id):
        return self.players.get((guild_id, event_id, user_id))

    async def save_player(self, player):
        self.players[(player.guild_id, player.event_id, player.user_id)] = player

    async def get_next_number(self, guild_id, event_id):
        count = sum(1 for (g, e, _) in self.players if g == guild_id and e == event_id)
        return f"{count + 1:03d}"

    async def list_players(self, guild_id, event_id, alive_only=False):
        players = [p for (g, e, _), p in self.players.items() if g == guild_id and e == event_id]
        if alive_only:
            players = [p for p in players if p.is_alive]
        return sorted(players, key=lambda p: p.player_number)

    async def clear_votes(self, guild_id, event_id):
        self.votes = [v for v in self.votes if not (v.guild_id == guild_id and v.event_id == event_id)]

    async def record_vote(self, vote):
        self.votes.append(vote)


class FakeBank:
    def __init__(self, balances=None):
        self.balances = dict(balances or {})
        self.transfers = []

    async def transfer(self, guild_id, from_user, to_user, amount, reason=""):
        if from_user != "__treasury__" and self.balances.get(from_user, 0) < amount:
            raise InsufficientFunds(f"{from_user} holds {self.balances.get(from_user, 0)} spi")
        self.balances[from_user] = self.balances.get(from_user, 0) - amount
        self.balances[to_user] = self.balances.get(to_user, 0) + amount
        self.transfers.append((from_user, to_user, amount, reason))


class TestArenaService(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.repo = InMemoryGamesRepository()
        self.service = ArenaService(self.repo)

    async def test_open_event(self):
        event = await self.service.open_event("g1")
        self.assertEqual(event.status, REGISTERING)
        self.assertEqual(event.entry_fee, 100)
        self.assertEqual(event.guild_id, "g1")

    async def test_open_event_custom_fee(self):
        event = await self.service.open_event("g1", entry_fee=250)
        self.assertEqual(event.entry_fee, 250)

    async def test_open_second_event_rejected(self):
        await self.service.open_event("g1")
        with self.assertRaises(ValidationError):
            await self.service.open_event("g1")

    async def test_join_event_charges_fee_and_credits_pot(self):
        bank = FakeBank({"u1": 500})
        self.service.attach_bank(bank)
        await self.service.open_event("g1", entry_fee=100)

        player = await self.service.join_event("g1", "u1")
        self.assertEqual(player.player_number, "001")
        self.assertEqual(player.display_tag, "Player 001")

        event = await self.service.get_active_event("g1")
        self.assertEqual(event.pot_amount, 100)
        self.assertIn(("u1", POT, 100, "arena entry fee"), bank.transfers)

    async def test_join_event_insufficient_funds(self):
        bank = FakeBank({"u1": 0})
        self.service.attach_bank(bank)
        await self.service.open_event("g1", entry_fee=100)
        with self.assertRaises(ValidationError):
            await self.service.join_event("g1", "u1")

    async def test_join_event_idempotent(self):
        bank = FakeBank({"u1": 500})
        self.service.attach_bank(bank)
        await self.service.open_event("g1", entry_fee=100)

        p1 = await self.service.join_event("g1", "u1")
        p2 = await self.service.join_event("g1", "u1")
        self.assertEqual(p1.player_number, p2.player_number)
        self.assertEqual(len(bank.transfers), 1)

        event = await self.service.get_active_event("g1")
        self.assertEqual(event.pot_amount, 100)

    async def test_start_event_requires_players(self):
        await self.service.open_event("g1")
        with self.assertRaises(ValidationError):
            await self.service.start_event("g1")

    async def test_start_event_begins_tracking(self):
        await self.service.open_event("g1")
        await self.service.join_event("g1", "u1")
        event = await self.service.start_event("g1")
        self.assertEqual(event.status, ONGOING)
        self.assertTrue(self.service.game.is_active("g1"))

    async def test_eliminate_player(self):
        await self.service.open_event("g1", entry_fee=100)
        await self.service.join_event("g1", "u1")
        await self.service.start_event("g1")

        result = await self.service.eliminate_player("g1", "u1", "moved")
        self.assertEqual(result.player_number, "001")
        self.assertEqual(result.user_id, "u1")
        self.assertEqual(result.reason, "moved")

        event = await self.service.get_active_event("g1")
        player = await self.repo.get_player("g1", event.event_id, "u1")
        self.assertFalse(player.is_alive)
        self.assertEqual(player.elimination_reason, "moved")

    async def test_conclude_event_winner_takes_all(self):
        bank = FakeBank({"u1": 500, "u2": 500})
        self.service.attach_bank(bank)
        await self.service.open_event("g1", entry_fee=100)
        await self.service.join_event("g1", "u1")
        await self.service.join_event("g1", "u2")
        await self.service.start_event("g1")
        await self.service.eliminate_player("g1", "u2", "moved")

        result = await self.service.conclude_event("g1")
        self.assertEqual(result.winner_id, "u1")
        self.assertEqual(result.pot_total, 200)
        self.assertEqual(result.payout_per_survivor, 200)
        self.assertIn((POT, "u1", 200, "arena payout"), bank.transfers)

    async def test_conclude_event_splits_pot(self):
        bank = FakeBank({"u1": 500, "u2": 500})
        self.service.attach_bank(bank)
        await self.service.open_event("g1", entry_fee=100)
        await self.service.join_event("g1", "u1")
        await self.service.join_event("g1", "u2")
        await self.service.start_event("g1")

        result = await self.service.conclude_event("g1")
        self.assertIsNone(result.winner_id)
        self.assertEqual(result.survivor_count, 2)
        self.assertEqual(result.payout_per_survivor, 100)
        self.assertIn((POT, "u1", 100, "arena payout"), bank.transfers)
        self.assertIn((POT, "u2", 100, "arena payout"), bank.transfers)

    async def test_conclude_total_extinction_carries_pot(self):
        bank = FakeBank({"u1": 500})
        self.service.attach_bank(bank)
        await self.service.open_event("g1", entry_fee=100)
        await self.service.join_event("g1", "u1")
        await self.service.start_event("g1")
        await self.service.eliminate_player("g1", "u1", "moved")

        result = await self.service.conclude_event("g1")
        self.assertEqual(result.survivor_count, 0)
        self.assertIsNone(result.winner_id)
        # No payout transfers on total extinction
        payout_transfers = [t for t in bank.transfers if t[0] == POT and t[3] == "arena payout"]
        self.assertEqual(len(payout_transfers), 0)

    async def test_get_status(self):
        bank = FakeBank({"u1": 500})
        self.service.attach_bank(bank)
        await self.service.open_event("g1", entry_fee=100)
        await self.service.join_event("g1", "u1")

        status = await self.service.get_status("g1")
        self.assertEqual(status.status, REGISTERING)
        self.assertEqual(status.total_players, 1)
        self.assertEqual(status.alive_count, 1)
        self.assertEqual(status.pot_amount, 100)

    async def test_vote_records_choice(self):
        await self.service.open_event("g1")
        await self.service.join_event("g1", "u1")
        await self.service.start_event("g1")
        await self.service.open_voting("g1")

        vote = await self.service.vote("g1", "u1", "stop")
        self.assertEqual(vote.choice, "stop")
        self.assertEqual(len(self.repo.votes), 1)