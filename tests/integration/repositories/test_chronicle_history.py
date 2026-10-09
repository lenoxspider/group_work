"""Tests for chronicle history reconstruction.

The reconstruction reads the ledger the server already keeps - it must not
invent anything, must stamp each entry with its original date, must come back
in chronological order, and must be idempotent so running it twice cannot
duplicate the country's history.
"""

import os
import tempfile
import unittest

import aiosqlite

from src.infrastructure.database.connection import DatabaseManager
from src.plugins.bank.schema import BANK_SCHEMA
from src.plugins.chronicle.history import reconstruct
from src.plugins.chronicle.repository import SQLiteChronicleRepository
from src.plugins.chronicle.schema import CHRONICLE_SCHEMA
from src.plugins.chronicle.service import ChronicleService
from src.plugins.community.schema import COMMUNITY_MIGRATIONS, COMMUNITY_SCHEMA
from src.plugins.games.schema import GAMES_SCHEMA
from src.plugins.society.schema import SOCIETY_SCHEMA

GUILD = "guild-history"


class TestChronicleReconstruction(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        mgr = DatabaseManager(self.db_path)
        mgr.register_plugin_schema("bank", BANK_SCHEMA)
        mgr.register_plugin_schema("chronicle", CHRONICLE_SCHEMA)
        mgr.register_plugin_schema("community", COMMUNITY_SCHEMA)
        mgr.register_plugin_migrations("community", COMMUNITY_MIGRATIONS)
        mgr.register_plugin_schema("games", GAMES_SCHEMA)
        mgr.register_plugin_schema("society", SOCIETY_SCHEMA)
        await mgr.initialize_schema()
        await self._seed()

    async def asyncTearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    async def _seed(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO member_registry (guild_id, user_id, status, intro_done, joined_at, signed_at) "
                "VALUES (?,?,?,?,?,?)",
                (GUILD, "founder", "citizen", 1, "2026-09-27T10:00:00+00:00", "2026-09-28T12:00:00+00:00"))
            await db.execute(
                "INSERT INTO laws (law_id, guild_id, title, description, fine_amount, created_at) "
                "VALUES (?,?,?,?,?,?)",
                ("LAW-1", GUILD, "The Law of the Hall", "desc", 15, "2026-09-27T11:00:00+00:00"))
            await db.execute(
                "INSERT INTO games_events (event_id, guild_id, status, pot_amount, winner_id, concluded_at) "
                "VALUES (?,?,?,?,?,?)",
                ("EV-1", GUILD, "CONCLUDED", 500, "founder", "2026-10-08T21:00:00+00:00"))
            await db.execute(
                "INSERT INTO court_cases (case_id, guild_id, accuser_id, accused_id, law_id, status, created_at, opened_at, resolved_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                ("CASE-1", GUILD, "founder", "accused1", "LAW-1", "CONVICTED", "2026-09-29T09:00:00+00:00", "2026-09-29T09:00:00+00:00", "2026-09-30T09:00:00+00:00"))
            await db.execute(
                "INSERT INTO bank_transactions (tx_id, guild_id, from_user, to_user, amount, reason, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                ("tx1", GUILD, "accused1", "__treasury__", 50, "snap trial fine", "2026-10-06T19:00:00+00:00"))
            await db.commit()

    async def test_reconstructs_the_known_history(self):
        entries = await reconstruct(self.db_path, GUILD)
        kinds = [e[0] for e in entries]
        self.assertIn("founding", kinds)
        self.assertIn("law_enacted", kinds)
        self.assertIn("citizen_signed", kinds)
        self.assertIn("games_concluded", kinds)
        self.assertIn("court_verdict", kinds)
        self.assertIn("snap_trial", kinds)

    async def test_entries_are_chronological(self):
        entries = await reconstruct(self.db_path, GUILD)
        stamps = [e[2] for e in entries]
        self.assertEqual(stamps, sorted(stamps))

    async def test_each_entry_carries_its_original_date(self):
        entries = await reconstruct(self.db_path, GUILD)
        law = next(e for e in entries if e[0] == "law_enacted")
        self.assertIn("2026-09-27", law[1])
        games = next(e for e in entries if e[0] == "games_concluded")
        self.assertIn("2026-10-08", games[1])

    async def test_the_winner_and_pot_are_named(self):
        entries = await reconstruct(self.db_path, GUILD)
        games = next(e for e in entries if e[0] == "games_concluded")
        self.assertIn("<@founder>", games[1])
        self.assertIn("500", games[1])

    async def test_reconstruct_history_is_idempotent(self):
        service = ChronicleService(SQLiteChronicleRepository(self.db_path))
        first = await service.reconstruct_history(GUILD)
        self.assertGreater(first, 0)
        second = await service.reconstruct_history(GUILD)
        self.assertEqual(second, 0, "a second reconstruction must not duplicate history")

    async def test_an_empty_server_reconstructs_nothing(self):
        entries = await reconstruct(self.db_path, "some-other-guild")
        self.assertEqual(entries, [])

    async def test_an_open_proposal_is_not_reconstructed_as_resolved(self):
        """The bug this guards: resolved_at='' is not NULL, so IS NOT NULL alone
        let an still-open proposal through and recorded it as rejected."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO proposals (proposal_id, guild_id, author_id, title, description, "
                "status, approvals, rejections, created_at, resolved_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("PROP-OPEN", GUILD, "author", "An Open Proposal", "desc",
                 "OPEN", "", "", "2026-10-06T00:00:00+00:00", ""))
            await db.commit()
        entries = await reconstruct(self.db_path, GUILD)
        self.assertNotIn("proposal_concluded", [e[0] for e in entries])

    async def test_a_resolved_proposal_is_reconstructed(self):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO proposals (proposal_id, guild_id, author_id, title, description, "
                "status, approvals, rejections, created_at, resolved_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                ("PROP-DONE", GUILD, "author", "A Passed Proposal", "desc",
                 "APPROVED", "a,b", "", "2026-10-06T00:00:00+00:00", "2026-10-07T00:00:00+00:00"))
            await db.commit()
        entries = await reconstruct(self.db_path, GUILD)
        prop = next((e for e in entries if e[0] == "proposal_concluded"), None)
        self.assertIsNotNone(prop)
        self.assertIn("passed", prop[1])


if __name__ == "__main__":
    unittest.main()
