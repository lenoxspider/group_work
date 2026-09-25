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

    async def test_update_progress(self):
        now = datetime.now(timezone.utc)
        task = Task(
            task_id="TASK-T03",
            guild_id="guild-100",
            channel_id=None,
            message_id=None,
            description="Progress test",
            assigned_to="user-400",
            due_date=now + timedelta(days=1),
            created_at=now
        )
        await self.repo.save(task)
        await self.repo.update_progress("TASK-T03", True)

        updated = await self.repo.get_by_id("TASK-T03")
        self.assertTrue(updated.is_in_progress)

    async def test_get_overdue_unshamed_and_mark_shame_logged(self):
        now = datetime.now(timezone.utc)
        overdue_task = Task(
            task_id="TASK-T04",
            guild_id="guild-100",
            channel_id=None,
            message_id=None,
            description="Overdue test",
            assigned_to="user-400",
            due_date=now - timedelta(hours=2),
            created_at=now - timedelta(days=1)
        )
        await self.repo.save(overdue_task)

        unshamed = await self.repo.get_overdue_unshamed(now)
        self.assertEqual(len(unshamed), 1)
        self.assertEqual(unshamed[0].task_id, "TASK-T04")

        await self.repo.mark_shame_logged("TASK-T04")
        unshamed_after = await self.repo.get_overdue_unshamed(now)
        self.assertEqual(len(unshamed_after), 0)

if __name__ == "__main__":
    unittest.main()
