"""Integration tests for SQLiteProjectRepository."""

import os
import tempfile
import unittest

from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.database.project_sqlite_repo import SQLiteProjectRepository
from src.domain.entities.project_state import ProjectState, ProjectStatus

class TestSQLiteProjectRepository(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.temp_file.close()
        self.db_manager = DatabaseManager(self.temp_file.name)
        await self.db_manager.initialize_schema()
        self.repo = SQLiteProjectRepository(self.temp_file.name)

    async def asyncTearDown(self):
        if os.path.exists(self.temp_file.name):
            os.remove(self.temp_file.name)

    async def test_save_and_retrieve_project_state(self):
        state = ProjectState(guild_id="guild-999")
        state.archive("Instructor")

        await self.repo.save_state(state)
        retrieved = await self.repo.get_state("guild-999")

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.guild_id, "guild-999")
        self.assertEqual(retrieved.status, ProjectStatus.ARCHIVED)
        self.assertEqual(retrieved.archived_by, "Instructor")
        self.assertIsNotNone(retrieved.archived_at)

if __name__ == "__main__":
    unittest.main()
