"""Integration tests for SQLitePreferenceRepository."""

import os
import tempfile
import unittest
from datetime import datetime, timezone

from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.database.preference_sqlite_repo import SQLitePreferenceRepository
from src.domain.entities.member_preference import MemberPreference

class TestSQLitePreferenceRepository(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.temp_file.close()
        self.db_manager = DatabaseManager(self.temp_file.name)
        await self.db_manager.initialize_schema()
        self.repo = SQLitePreferenceRepository(self.temp_file.name)

    async def asyncTearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    async def test_save_and_retrieve_preference(self):
        pref = MemberPreference(
            guild_id="guild-100",
            user_id="user-200",
            timezone_name="America/New_York",
            quiet_hours_start=22,
            quiet_hours_end=7,
            updated_at=datetime.now(timezone.utc)
        )
        await self.repo.save(pref)

        retrieved = await self.repo.get_preference("guild-100", "user-200")
        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.guild_id, "guild-100")
        self.assertEqual(retrieved.user_id, "user-200")
        self.assertEqual(retrieved.timezone_name, "America/New_York")
        self.assertEqual(retrieved.quiet_hours_start, 22)
        self.assertEqual(retrieved.quiet_hours_end, 7)

    async def test_update_existing_preference(self):
        pref = MemberPreference(
            guild_id="guild-100",
            user_id="user-200",
            timezone_name="UTC",
            quiet_hours_start=23,
            quiet_hours_end=8
        )
        await self.repo.save(pref)

        pref.timezone_name = "Europe/London"
        pref.quiet_hours_start = 0
        pref.quiet_hours_end = 6
        await self.repo.save(pref)

        updated = await self.repo.get_preference("guild-100", "user-200")
        self.assertIsNotNone(updated)
        self.assertEqual(updated.timezone_name, "Europe/London")
        self.assertEqual(updated.quiet_hours_start, 0)
        self.assertEqual(updated.quiet_hours_end, 6)

    async def test_get_nonexistent_returns_none(self):
        result = await self.repo.get_preference("guild-none", "user-none")
        self.assertIsNone(result)

if __name__ == "__main__":
    unittest.main()
