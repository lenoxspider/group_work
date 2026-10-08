"""Tests for the Chronicle - the state's memory.

Two things matter here. The repository/service must record, queue for posting,
and never let a failed record break the action that triggered it. And the
cross-plugin wiring must actually fire: a citizen signing has to land an entry
without the community service knowing anything about Discord.
"""

import os
import tempfile
import unittest

from src.infrastructure.database.connection import DatabaseManager
from src.plugins.chronicle.repository import SQLiteChronicleRepository
from src.plugins.chronicle.schema import CHRONICLE_SCHEMA
from src.plugins.chronicle.service import ChronicleService
from src.plugins.community.repository import SQLiteCommunityRepository
from src.plugins.community.schema import COMMUNITY_MIGRATIONS, COMMUNITY_SCHEMA
from src.plugins.community.service import CommunityService

GUILD = "guild-chronicle"


class ChronicleTestBase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        manager = DatabaseManager(self.db_path)
        manager.register_plugin_schema("chronicle", CHRONICLE_SCHEMA)
        manager.register_plugin_schema("community", COMMUNITY_SCHEMA)
        manager.register_plugin_migrations("community", COMMUNITY_MIGRATIONS)
        await manager.initialize_schema()
        self.repo = SQLiteChronicleRepository(self.db_path)
        self.chron = ChronicleService(self.repo)

    async def asyncTearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass


class TestChronicleStore(ChronicleTestBase):
    async def test_record_queues_an_unposted_entry(self):
        await self.chron.record(GUILD, "citizen_signed", "someone signed")
        unposted = await self.repo.list_unposted()
        self.assertEqual(len(unposted), 1)
        self.assertEqual(unposted[0]["text"], "someone signed")
        self.assertEqual(unposted[0]["kind"], "citizen_signed")

    async def test_mark_posted_drains_the_queue(self):
        await self.chron.record(GUILD, "law_enacted", "x")
        entry = (await self.repo.list_unposted())[0]
        await self.repo.mark_posted(entry["id"])
        self.assertEqual(await self.repo.list_unposted(), [])

    async def test_recent_reads_oldest_first(self):
        await self.chron.record(GUILD, "a", "first")
        await self.chron.record(GUILD, "b", "second")
        recent = await self.chron.recent(GUILD, 10)
        self.assertEqual([e["text"] for e in recent], ["first", "second"])

    async def test_recent_is_scoped_to_the_guild(self):
        await self.chron.record("g1", "a", "one")
        await self.chron.record("g2", "a", "two")
        self.assertEqual([e["text"] for e in await self.chron.recent("g1", 10)], ["one"])

    async def test_recent_respects_the_limit(self):
        for i in range(5):
            await self.chron.record(GUILD, "a", f"e{i}")
        self.assertEqual(len(await self.chron.recent(GUILD, 2)), 2)

    async def test_counts_by_kind(self):
        await self.chron.record(GUILD, "snap_trial", "1")
        await self.chron.record(GUILD, "snap_trial", "2")
        await self.chron.record(GUILD, "law_enacted", "3")
        self.assertEqual(await self.chron.counts(GUILD), {"snap_trial": 2, "law_enacted": 1})

    async def test_record_never_raises_even_if_the_store_is_broken(self):
        """The whole point: a failed history write must not break a signing."""
        class Broken:
            async def add(self, *args, **kwargs):
                raise RuntimeError("database is locked")

        service = ChronicleService(Broken())
        await service.record(GUILD, "x", "y")  # must not raise


class TestChronicleWiring(ChronicleTestBase):
    async def test_signing_the_constitution_lands_a_chronicle_entry(self):
        community = CommunityService(SQLiteCommunityRepository(self.db_path))
        community.attach_chronicle(self.chron)

        await community.sign(GUILD, "u1")

        entries = await self.chron.recent(GUILD, 10)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["kind"], "citizen_signed")
        self.assertIn("<@u1>", entries[0]["text"])

    async def test_an_already_signed_citizen_does_not_record_again(self):
        community = CommunityService(SQLiteCommunityRepository(self.db_path))
        community.attach_chronicle(self.chron)
        await community.sign(GUILD, "u1")
        await community.sign(GUILD, "u1")  # second call is a no-op
        self.assertEqual(len(await self.chron.recent(GUILD, 10)), 1)

    async def test_signing_without_a_chronicle_still_works(self):
        """The chronicle is optional; its absence must not break onboarding."""
        community = CommunityService(SQLiteCommunityRepository(self.db_path))
        member = await community.sign(GUILD, "u1")
        self.assertEqual(member.status, "citizen")


if __name__ == "__main__":
    unittest.main()
