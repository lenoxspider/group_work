"""Integration tests for SQLiteActivityRepository."""

import os
import tempfile
import unittest

from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.database.activity_sqlite_repo import SQLiteActivityRepository

class TestSQLiteActivityRepository(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.temp_file.close()
        self.db_manager = DatabaseManager(self.temp_file.name)
        await self.db_manager.initialize_schema()
        self.repo = SQLiteActivityRepository(self.temp_file.name)

    async def asyncTearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    async def test_record_message_and_retrieve_activity(self):
        await self.repo.record_message("guild-1", "user-1")
        await self.repo.record_message("guild-1", "user-1")

        act = await self.repo.get_activity("guild-1", "user-1")
        self.assertIsNotNone(act)
        self.assertEqual(act.message_count, 2)
        self.assertEqual(act.files_submitted, 0)

    async def test_record_file_submission(self):
        await self.repo.record_file_submission("guild-1", "user-1")
        act = await self.repo.get_activity("guild-1", "user-1")
        self.assertEqual(act.files_submitted, 1)

    async def test_guild_standings_ranking(self):
        # User 1: 1 completed task (score = 3.0)
        await self.repo.record_task_completed("guild-1", "user-1")
        # User 2: 10 messages (score = 1.0)
        for _ in range(10):
            await self.repo.record_message("guild-1", "user-2")

        standings = await self.repo.get_guild_standings("guild-1")
        self.assertEqual(len(standings), 2)
        self.assertEqual(standings[0].user_id, "user-1")
        self.assertEqual(standings[1].user_id, "user-2")

if __name__ == "__main__":
    unittest.main()
