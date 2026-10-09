"""Unit tests for the offices of state.

The invariants that matter: one holder per office, appointing replaces and
reports who it displaced, a member may hold several offices, vacating an empty
office is a no-op, and every change is recorded in the chronicle - because an
office changing hands is exactly what the state should remember.
"""

import os
import tempfile
import unittest

from src.infrastructure.database.connection import DatabaseManager
from src.plugins.offices.domain import FRONT_MAN, MAGISTRATE, TREASURER
from src.plugins.offices.repository import SQLiteOfficesRepository
from src.plugins.offices.schema import OFFICES_SCHEMA
from src.plugins.offices.service import OfficeError, OfficesService

GUILD = "guild-offices"


class FakeChronicle:
    def __init__(self):
        self.entries = []

    async def record(self, guild_id, kind, text):
        self.entries.append((kind, text))


class TestOfficesService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        manager = DatabaseManager(self.db_path)
        manager.register_plugin_schema("offices", OFFICES_SCHEMA)
        await manager.initialize_schema()
        self.repo = SQLiteOfficesRepository(self.db_path)
        self.chron = FakeChronicle()
        self.svc = OfficesService(self.repo)
        self.svc.attach_chronicle(self.chron)

    async def asyncTearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    async def test_appoint_sets_the_holder(self):
        previous = await self.svc.appoint(GUILD, MAGISTRATE, "u1", "admin")
        self.assertIsNone(previous)
        self.assertEqual(await self.svc.holder(GUILD, MAGISTRATE), "u1")
        self.assertTrue(await self.svc.holds(GUILD, "u1", MAGISTRATE))

    async def test_appointing_replaces_and_reports_the_displaced(self):
        await self.svc.appoint(GUILD, MAGISTRATE, "u1")
        previous = await self.svc.appoint(GUILD, MAGISTRATE, "u2")
        self.assertEqual(previous, "u1")
        self.assertEqual(await self.svc.holder(GUILD, MAGISTRATE), "u2")
        self.assertFalse(await self.svc.holds(GUILD, "u1", MAGISTRATE))

    async def test_only_one_holder_per_office(self):
        await self.svc.appoint(GUILD, MAGISTRATE, "u1")
        await self.svc.appoint(GUILD, MAGISTRATE, "u2")
        rows = [r for r in await self.repo.all_offices(GUILD) if r["office"] == MAGISTRATE]
        self.assertEqual(len(rows), 1)

    async def test_a_member_may_hold_several_offices(self):
        await self.svc.appoint(GUILD, MAGISTRATE, "u1")
        await self.svc.appoint(GUILD, TREASURER, "u1")
        self.assertEqual(
            sorted(await self.svc.offices_held_by(GUILD, "u1")),
            sorted([MAGISTRATE, TREASURER]),
        )

    async def test_vacate_removes_and_reports_the_previous(self):
        await self.svc.appoint(GUILD, FRONT_MAN, "u1")
        previous = await self.svc.vacate(GUILD, FRONT_MAN)
        self.assertEqual(previous, "u1")
        self.assertIsNone(await self.svc.holder(GUILD, FRONT_MAN))

    async def test_vacating_an_empty_office_is_a_noop(self):
        self.assertIsNone(await self.svc.vacate(GUILD, TREASURER))
        self.assertEqual(self.chron.entries, [], "an empty vacate records nothing")

    async def test_invalid_office_is_refused(self):
        with self.assertRaises(OfficeError):
            await self.svc.appoint(GUILD, "emperor", "u1")
        with self.assertRaises(OfficeError):
            await self.svc.vacate(GUILD, "emperor")

    async def test_appointment_is_recorded_in_the_chronicle(self):
        await self.svc.appoint(GUILD, MAGISTRATE, "u1")
        self.assertEqual(self.chron.entries[0][0], "office_appointed")
        self.assertIn("<@u1>", self.chron.entries[0][1])
        self.assertIn("Magistrate", self.chron.entries[0][1])

    async def test_vacation_is_recorded_in_the_chronicle(self):
        await self.svc.appoint(GUILD, TREASURER, "u1")
        self.chron.entries.clear()
        await self.svc.vacate(GUILD, TREASURER)
        self.assertEqual(self.chron.entries[0][0], "office_vacated")

    async def test_offices_are_scoped_to_the_guild(self):
        await self.svc.appoint("g1", MAGISTRATE, "u1")
        self.assertIsNone(await self.svc.holder("g2", MAGISTRATE))

    async def test_all_offices_lists_every_holder(self):
        await self.svc.appoint(GUILD, MAGISTRATE, "u1")
        await self.svc.appoint(GUILD, TREASURER, "u2")
        rows = await self.svc.all_offices(GUILD)
        self.assertEqual(
            {r["office"]: r["user_id"] for r in rows},
            {MAGISTRATE: "u1", TREASURER: "u2"},
        )


if __name__ == "__main__":
    unittest.main()
