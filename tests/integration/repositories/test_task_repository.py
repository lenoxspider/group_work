"""Integration tests for SQLiteTaskRepository."""

import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.database.task_sqlite_repo import SQLiteTaskRepository
from src.domain.entities.task import Task

class TestSQLiteTaskRepository(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.temp_file.close()
        self.db_manager = DatabaseManager(self.temp_file.name)
        await self.db_manager.initialize_schema()
        self.repo = SQLiteTaskRepository(self.temp_file.name)

    async def asyncTearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    async def test_save_and_retrieve_task(self):
        now = datetime.now(timezone.utc)
        task = Task(
            task_id="TASK-T01",
            guild_id="guild-100",
            channel_id="chan-200",
            message_id="msg-300",
            description="Integration test deliverable",
            assigned_to="user-400",
            due_date=now + timedelta(days=3),
            created_at=now
        )

        await self.repo.save(task)
        retrieved = await self.repo.get_by_id("TASK-T01")

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.task_id, "TASK-T01")
        self.assertEqual(retrieved.description, "Integration test deliverable")
        self.assertFalse(retrieved.is_completed)

    async def test_update_reminder_tier(self):
        now = datetime.now(timezone.utc)
        task = Task(
            task_id="TASK-T02",
            guild_id="guild-100",
            channel_id=None,
            message_id=None,
            description="Reminder test",
            assigned_to="user-400",
            due_date=now + timedelta(days=1),
            created_at=now
        )
        await self.repo.save(task)
        await self.repo.update_reminder("TASK-T02", "24h")

        updated = await self.repo.get_by_id("TASK-T02")
        self.assertTrue(updated.reminded_24h)
        self.assertFalse(updated.reminded_1h)

if __name__ == "__main__":
    unittest.main()
