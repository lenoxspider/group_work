"""Unit tests for TaskService with mocked repositories."""

import unittest
from unittest.mock import AsyncMock
from datetime import datetime, timezone, timedelta

from src.application.services.task_service import TaskService
from src.application.dtos.task_dtos import CreateTaskDTO
from src.domain.errors import ValidationError, NotFoundError
from tests.fixtures.factories import make_task

class TestTaskService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_task_repo = AsyncMock()
        self.mock_activity_repo = AsyncMock()
        self.service = TaskService(self.mock_task_repo, self.mock_activity_repo)

    async def test_create_task_success(self):
        due = datetime.now(timezone.utc) + timedelta(days=2)
        dto = CreateTaskDTO(
            guild_id="guild-1",
            description="Write literature review",
            assigned_to="user-1",
            due_date=due
        )

        result = await self.service.create_task(dto)
        self.assertTrue(result.task_id.startswith("TASK-"))
        self.assertEqual(result.description, "Write literature review")
        self.mock_task_repo.save.assert_awaited_once()

    async def test_create_task_past_due_raises_validation_error(self):
        past_due = datetime.now(timezone.utc) - timedelta(days=1)
        dto = CreateTaskDTO(
            guild_id="guild-1",
            description="Past task",
            assigned_to="user-1",
            due_date=past_due
        )

        with self.assertRaises(ValidationError):
            await self.service.create_task(dto)

    async def test_complete_task_success(self):
        task = make_task(task_id="TASK-99", is_completed=False)
        self.mock_task_repo.get_by_id.return_value = task

        result = await self.service.complete_task("TASK-99")
        self.assertTrue(result.is_completed)
        self.mock_task_repo.save.assert_awaited_once()
        self.mock_activity_repo.record_task_completed.assert_awaited_once_with(task.guild_id, task.assigned_to)

    async def test_complete_nonexistent_task_raises_not_found(self):
        self.mock_task_repo.get_by_id.return_value = None
        with self.assertRaises(NotFoundError):
            await self.service.complete_task("TASK-MISSING")

if __name__ == "__main__":
    unittest.main()
