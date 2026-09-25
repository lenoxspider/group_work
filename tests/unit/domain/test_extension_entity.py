"""Unit tests for ExtensionRequest entity."""

import unittest
from datetime import datetime, timezone, timedelta
from src.domain.entities.extension_request import ExtensionRequest
from src.domain.errors import ValidationError

class TestExtensionRequestEntity(unittest.TestCase):

    def _make_extension(self, requester: str = "user-1") -> ExtensionRequest:
        now = datetime.now(timezone.utc)
        return ExtensionRequest(
            request_id="EXT-1234",
            task_id="TASK-99",
            guild_id="guild-1",
            requester_id=requester,
            proposed_due_date=now + timedelta(days=2),
            reason="Illness and midterms",
            created_at=now
        )

    def test_extension_creation_valid(self):
        ext = self._make_extension()
        self.assertEqual(ext.request_id, "EXT-1234")
        self.assertFalse(ext.is_resolved)
        self.assertEqual(ext.total_votes, 0)

    def test_requester_cannot_vote_on_own_request(self):
        ext = self._make_extension(requester="user-alice")
        with self.assertRaises(ValidationError):
            ext.cast_vote(user_id="user-alice", approve=True)

    def test_cast_vote_approvals_and_rejections(self):
        ext = self._make_extension()
        ext.cast_vote("user-bob", approve=True)
        ext.cast_vote("user-charlie", approve=False)
        self.assertEqual(len(ext.approvals), 1)
        self.assertEqual(len(ext.rejections), 1)
        self.assertEqual(ext.total_votes, 2)

        # Charlie flips vote to approve
        ext.cast_vote("user-charlie", approve=True)
        self.assertEqual(len(ext.approvals), 2)
        self.assertEqual(len(ext.rejections), 0)

    def test_resolve_majority_approved(self):
        ext = self._make_extension()
        ext.cast_vote("user-2", approve=True)
        ext.cast_vote("user-3", approve=True)
        ext.cast_vote("user-4", approve=False)

        approved = ext.resolve_majority()
        self.assertTrue(approved)
        self.assertEqual(ext.status, "APPROVED")
        self.assertTrue(ext.is_resolved)

    def test_resolve_majority_rejected_or_tied(self):
        ext = self._make_extension()
        ext.cast_vote("user-2", approve=True)
        ext.cast_vote("user-3", approve=False)

        approved = ext.resolve_majority()
        self.assertFalse(approved)
        self.assertEqual(ext.status, "REJECTED")

    def test_cannot_vote_after_resolved(self):
        ext = self._make_extension()
        ext.cast_vote("user-2", approve=True)
        ext.resolve_majority()

        with self.assertRaises(ValidationError):
            ext.cast_vote("user-3", approve=True)

if __name__ == "__main__":
    unittest.main()
