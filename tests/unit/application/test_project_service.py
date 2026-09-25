"""Unit tests for ProjectService with mocked repositories."""

import unittest
from unittest.mock import AsyncMock
from datetime import datetime, timezone, timedelta

from src.application.services.project_service import ProjectService
from src.domain.entities.project_state import ProjectState, ProjectStatus
from src.domain.entities.member_activity import MemberActivity
from tests.fixtures.factories import make_task, make_deadline

class TestProjectService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_project_repo = AsyncMock()
        self.mock_task_repo = AsyncMock()
        self.mock_deadline_repo = AsyncMock()
        self.mock_activity_repo = AsyncMock()

        self.service = ProjectService(
            self.mock_project_repo,
            self.mock_task_repo,
            self.mock_deadline_repo,
            self.mock_activity_repo
        )

    async def test_get_project_status(self):
        self.mock_project_repo.get_state.return_value = ProjectState(guild_id="guild-1")
        self.mock_task_repo.get_pending_by_guild.return_value = [make_task(), make_task()]
        self.mock_deadline_repo.get_active_by_guild.return_value = [make_deadline(name="Midterm")]
        self.mock_activity_repo.get_guild_standings.return_value = [
            MemberActivity(guild_id="guild-1", user_id="user-1", tasks_completed=3, files_submitted=2)
        ]

        status = await self.service.get_project_status("guild-1")
        self.assertEqual(status.status, "ACTIVE")
        self.assertEqual(status.completed_tasks, 3)
        self.assertEqual(status.pending_tasks, 2)
        self.assertEqual(status.total_tasks, 5)
        self.assertEqual(status.nearest_deadline_name, "Midterm")

    async def test_archive_project(self):
        self.mock_project_repo.get_state.return_value = ProjectState(guild_id="guild-1")
        self.mock_activity_repo.get_guild_standings.return_value = [
            MemberActivity(guild_id="guild-1", user_id="user-1", tasks_completed=4, files_submitted=1)
        ]

        summary = await self.service.archive_project("guild-1", "Lead Dev")
        self.assertEqual(summary.archived_by, "Lead Dev")
        self.assertEqual(summary.total_tasks_completed, 4)
        self.assertEqual(summary.total_files_submitted, 1)
        self.mock_project_repo.save_state.assert_awaited_once()

if __name__ == "__main__":
    unittest.main()
