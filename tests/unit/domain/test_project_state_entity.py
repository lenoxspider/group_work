"""Unit tests for ProjectState entity."""

import unittest
from datetime import datetime, timezone
from src.domain.entities.project_state import ProjectState, ProjectStatus, ProjectAlreadyArchivedError
from src.domain.errors import ValidationError

class TestProjectStateEntity(unittest.TestCase):

    def test_project_state_creation_valid(self):
        state = ProjectState(guild_id="guild-100")
        self.assertEqual(state.guild_id, "guild-100")
        self.assertEqual(state.status, ProjectStatus.ACTIVE)
        self.assertFalse(state.is_archived)

    def test_empty_guild_id_raises_error(self):
        with self.assertRaises(ValidationError):
            ProjectState(guild_id="  ")

    def test_archive_project_success(self):
        state = ProjectState(guild_id="guild-100")
        now = datetime.now(timezone.utc)
        state.archive(archived_by_user_id="Team Lead", timestamp=now)
        self.assertTrue(state.is_archived)
        self.assertEqual(state.archived_by, "Team Lead")
        self.assertEqual(state.archived_at, now)

    def test_archive_already_archived_raises_error(self):
        state = ProjectState(guild_id="guild-100")
        state.archive(archived_by_user_id="Team Lead")
        with self.assertRaises(ProjectAlreadyArchivedError):
            state.archive(archived_by_user_id="Team Lead")

if __name__ == "__main__":
    unittest.main()
