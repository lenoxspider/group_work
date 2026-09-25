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
        self.assertTrue(result.is_on_time)
        self.mock_task_repo.save.assert_awaited_once()
        self.mock_activity_repo.record_task_completed.assert_awaited_once_with(
            task.guild_id, task.assigned_to, is_on_time=True
        )

    async def test_toggle_in_progress(self):
        task = make_task(task_id="TASK-100", is_completed=False, is_in_progress=False)
        self.mock_task_repo.get_by_id.return_value = task

        res = await self.service.toggle_in_progress("TASK-100")
        self.assertTrue(res.is_in_progress)
        self.mock_task_repo.update_progress.assert_awaited_once_with("TASK-100", True)

    async def test_evaluate_overdue_tasks_resets_streak(self):
        now = datetime.now(timezone.utc)
        overdue_task = make_task(task_id="TASK-OVERDUE", is_completed=False, hours_from_now=-5)
        self.mock_task_repo.get_overdue_unshamed.return_value = [overdue_task]

        shame_actions = await self.service.evaluate_overdue_tasks(now)
        self.assertEqual(len(shame_actions), 1)
        self.assertEqual(shame_actions[0].task_id, "TASK-OVERDUE")
        self.mock_activity_repo.reset_streak.assert_awaited_once_with(
            overdue_task.guild_id, overdue_task.assigned_to
        )

    async def test_complete_task_with_verifier_awaits_verification(self):
        task = make_task(
            task_id="TASK-VERIFY",
            is_completed=False,
            hours_from_now=5,
            verifier_id="verifier-999"
        )
        self.mock_task_repo.get_by_id.return_value = task

        result = await self.service.complete_task("TASK-VERIFY")
        self.assertTrue(result.is_completed)
        self.assertTrue(result.needs_verification)
        # Should NOT credit activity repo until verified
        self.mock_activity_repo.record_task_completed.assert_not_called()

    async def test_verify_task_awards_completion_and_buddy_bonus(self):
        task = make_task(
            task_id="TASK-VERIFY",
            is_completed=True,
            hours_from_now=5,
            verifier_id="verifier-999"
        )
        self.mock_task_repo.get_by_id.return_value = task

        result = await self.service.verify_task("TASK-VERIFY", "verifier-999")
        self.assertTrue(result.is_fully_verified)
        self.assertFalse(result.needs_verification)
        self.assertEqual(result.verified_by, "verifier-999")
        # Assignee credited
        self.mock_activity_repo.record_task_completed.assert_awaited_once_with(
            task.guild_id, task.assigned_to, is_on_time=True
        )
        # Verifier awarded buddy bonus
        self.mock_activity_repo.record_file_submission.assert_awaited_once_with(
            task.guild_id, "verifier-999"
        )

    async def test_complete_nonexistent_task_raises_not_found(self):
        self.mock_task_repo.get_by_id.return_value = None
        with self.assertRaises(NotFoundError):
            await self.service.complete_task("TASK-MISSING")

if __name__ == "__main__":
    unittest.main()
