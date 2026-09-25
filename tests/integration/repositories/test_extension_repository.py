"""Integration tests for SQLiteExtensionRepository."""

import os
import tempfile
import unittest
from datetime import datetime, timezone, timedelta

from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.database.extension_sqlite_repo import SQLiteExtensionRepository
from src.domain.entities.extension_request import ExtensionRequest

class TestSQLiteExtensionRepository(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.temp_file.close()
        self.db_manager = DatabaseManager(self.temp_file.name)
        await self.db_manager.initialize_schema()
        self.repo = SQLiteExtensionRepository(self.temp_file.name)

    async def asyncTearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    async def test_save_and_retrieve_extension(self):
        now = datetime.now(timezone.utc)
        ext = ExtensionRequest(
            request_id="EXT-INT01",
            task_id="TASK-INT01",
            guild_id="guild-100",
            requester_id="user-100",
            proposed_due_date=now + timedelta(days=3),
            reason="Integration test reason",
            created_at=now,
            approvals={"user-200", "user-300"},
            rejections={"user-400"}
        )

        await self.repo.save(ext)
        retrieved = await self.repo.get_by_id("EXT-INT01")

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.request_id, "EXT-INT01")
        self.assertEqual(retrieved.approvals, {"user-200", "user-300"})
        self.assertEqual(retrieved.rejections, {"user-400"})
        self.assertEqual(retrieved.status, "PENDING")

    async def test_get_pending_by_task(self):
        now = datetime.now(timezone.utc)
        ext = ExtensionRequest(
            request_id="EXT-INT02",
            task_id="TASK-INT02",
            guild_id="guild-100",
            requester_id="user-100",
            proposed_due_date=now + timedelta(days=2),
            reason="Testing pending lookup",
            created_at=now
        )
        await self.repo.save(ext)

        pending = await self.repo.get_pending_by_task("TASK-INT02")
        self.assertIsNotNone(pending)
        self.assertEqual(pending.request_id, "EXT-INT02")

if __name__ == "__main__":
    unittest.main()
