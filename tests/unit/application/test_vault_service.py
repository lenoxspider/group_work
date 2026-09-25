"""Unit tests for VaultService with mocked storage and repository."""

import unittest
from unittest.mock import AsyncMock

from src.application.services.vault_service import VaultService

class TestVaultService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_storage = AsyncMock()
        self.mock_activity_repo = AsyncMock()
        self.service = VaultService(self.mock_storage, self.mock_activity_repo)

    async def test_store_deliverable_success(self):
        self.mock_storage.store_file.return_value = (
            "draft_20260925_abcdef12.pdf",
            "abcdef1234567890",
            1024
        )

        result = await self.service.store_deliverable(
            guild_id="guild-1",
            user_id="user-1",
            filename="draft.pdf",
            content=b"file bytes"
        )

        self.assertEqual(result.stored_filename, "draft_20260925_abcdef12.pdf")
        self.assertEqual(result.file_hash, "abcdef1234567890")
        self.assertEqual(result.file_size, 1024)
        self.mock_storage.store_file.assert_awaited_once_with("draft.pdf", b"file bytes")
        self.mock_activity_repo.record_file_submission.assert_awaited_once_with("guild-1", "user-1")

if __name__ == "__main__":
    unittest.main()
