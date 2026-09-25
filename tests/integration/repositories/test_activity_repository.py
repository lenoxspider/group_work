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

    async def test_record_task_completed_streak_and_reset_streak(self):
        # 1st on-time task: streak = 1
        await self.repo.record_task_completed("guild-1", "user-3", is_on_time=True)
        act1 = await self.repo.get_activity("guild-1", "user-3")
        self.assertEqual(act1.current_streak, 1)
        self.assertEqual(act1.best_streak, 1)
        self.assertEqual(act1.on_time_tasks, 1)

        # 2nd on-time task: streak = 2
        await self.repo.record_task_completed("guild-1", "user-3", is_on_time=True)
        act2 = await self.repo.get_activity("guild-1", "user-3")
        self.assertEqual(act2.current_streak, 2)
        self.assertEqual(act2.best_streak, 2)
        self.assertEqual(act2.on_time_tasks, 2)

        # Overdue item triggers reset_streak: current = 0, best preserved
        await self.repo.reset_streak("guild-1", "user-3")
        act3 = await self.repo.get_activity("guild-1", "user-3")
        self.assertEqual(act3.current_streak, 0)
        self.assertEqual(act3.best_streak, 2)

        # 3rd task completed late: streak remains 0, tasks_completed increments
        await self.repo.record_task_completed("guild-1", "user-3", is_on_time=False)
        act4 = await self.repo.get_activity("guild-1", "user-3")
        self.assertEqual(act4.current_streak, 0)
        self.assertEqual(act4.best_streak, 2)
        self.assertEqual(act4.tasks_completed, 3)
        self.assertEqual(act4.on_time_tasks, 2)

if __name__ == "__main__":
    unittest.main()
