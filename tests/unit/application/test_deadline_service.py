"""Unit tests for DeadlineService with mocked repository."""

import unittest
from unittest.mock import AsyncMock
from datetime import datetime, timezone, timedelta

from src.application.services.deadline_service import DeadlineService
from src.application.dtos.deadline_dtos import CreateDeadlineDTO
from src.domain.errors import ValidationError, NotFoundError
from tests.fixtures.factories import make_deadline

class TestDeadlineService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_repo = AsyncMock()
        self.service = DeadlineService(self.mock_repo)

    async def test_schedule_deadline_success(self):
        due = datetime.now(timezone.utc) + timedelta(days=7)
        dto = CreateDeadlineDTO(
            guild_id="guild-1",
            channel_id="chan-1",
            message_id="msg-1",
            name="Final Paper Due",
            due_datetime=due
        )

        result = await self.service.schedule_deadline(dto)
        self.assertTrue(result.deadline_id.startswith("DL-"))
        self.assertEqual(result.name, "Final Paper Due")
        self.mock_repo.save.assert_awaited_once()

    async def test_schedule_deadline_past_raises_validation_error(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        dto = CreateDeadlineDTO(
            guild_id="guild-1",
            channel_id="chan-1",
            message_id="msg-1",
            name="Past Milestone",
            due_datetime=past
        )

        with self.assertRaises(ValidationError):
            await self.service.schedule_deadline(dto)

    async def test_complete_deadline_success(self):
        dl = make_deadline(deadline_id="DL-01", is_completed=False)
        self.mock_repo.get_by_id.return_value = dl

        result = await self.service.complete_deadline("DL-01")
        self.assertTrue(result.is_completed)
        self.mock_repo.save.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
