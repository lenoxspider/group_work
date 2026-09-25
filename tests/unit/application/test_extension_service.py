"""Unit tests for ExtensionService."""

import unittest
from unittest.mock import AsyncMock
from datetime import datetime, timezone, timedelta

from src.application.services.extension_service import ExtensionService
from src.application.dtos.extension_dtos import CreateExtensionDTO, CastVoteDTO
from src.domain.entities.extension_request import ExtensionRequest
from src.domain.errors import ValidationError, NotFoundError
from tests.fixtures.factories import make_task

class TestExtensionService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_ext_repo = AsyncMock()
        self.mock_task_repo = AsyncMock()
        self.service = ExtensionService(self.mock_ext_repo, self.mock_task_repo)

    async def test_request_extension_success(self):
        task = make_task(task_id="TASK-EXT01", assigned_to="user-1", hours_from_now=24)
        self.mock_task_repo.get_by_id.return_value = task
        self.mock_ext_repo.get_pending_by_task.return_value = None

        new_due = task.due_date + timedelta(days=2)
        dto = CreateExtensionDTO(
            task_id="TASK-EXT01",
            guild_id="guild-1",
            requester_id="user-1",
            proposed_due_date=new_due,
            reason="Need extra time for data cleaning"
        )

        result = await self.service.request_extension(dto)
        self.assertTrue(result.request_id.startswith("EXT-"))
        self.assertEqual(result.status, "PENDING")
        self.mock_ext_repo.save.assert_awaited_once()

    async def test_request_extension_non_assignee_raises_error(self):
        task = make_task(task_id="TASK-EXT01", assigned_to="user-1", hours_from_now=24)
        self.mock_task_repo.get_by_id.return_value = task
        self.mock_ext_repo.get_pending_by_task.return_value = None

        new_due = task.due_date + timedelta(days=2)
        dto = CreateExtensionDTO(
            task_id="TASK-EXT01",
            guild_id="guild-1",
            requester_id="user-imposter",
            proposed_due_date=new_due,
            reason="I am not the assignee"
        )

        with self.assertRaises(ValidationError):
            await self.service.request_extension(dto)

    async def test_conclude_vote_approved_extends_task(self):
        now = datetime.now(timezone.utc)
        ext = ExtensionRequest(
            request_id="EXT-VOTE01",
            task_id="TASK-VOTE01",
            guild_id="guild-1",
            requester_id="user-1",
            proposed_due_date=now + timedelta(days=5),
            reason="Server outage",
            created_at=now,
            approvals={"user-2", "user-3"},
            rejections={"user-4"}
        )
        self.mock_ext_repo.get_by_id.return_value = ext

        task = make_task(task_id="TASK-VOTE01", assigned_to="user-1", hours_from_now=24)
        self.mock_task_repo.get_by_id.return_value = task

        result = await self.service.conclude_vote("EXT-VOTE01", "user-1")
        self.assertTrue(result.is_approved)
        self.mock_task_repo.update_due_date.assert_awaited_once_with("TASK-VOTE01", ext.proposed_due_date)

if __name__ == "__main__":
    unittest.main()
