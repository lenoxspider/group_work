"""Unit tests for MemberActivity entity."""

import unittest
from src.domain.errors import ValidationError
from tests.fixtures.factories import make_activity

class TestMemberActivityEntity(unittest.TestCase):

    def test_activity_creation_valid(self):
        act = make_activity(messages=5, files=1, tasks_done=2)
        self.assertEqual(act.message_count, 5)
        self.assertEqual(act.files_submitted, 1)
        self.assertEqual(act.tasks_completed, 2)

    def test_empty_user_id_raises_error(self):
        with self.assertRaises(ValidationError):
            make_activity(user_id="  ")

    def test_record_message_increments_count(self):
        act = make_activity(messages=3)
        act.record_message()
        self.assertEqual(act.message_count, 4)

    def test_record_file_submission_increments_count(self):
        act = make_activity(files=0)
        act.record_file_submission()
        self.assertEqual(act.files_submitted, 1)

    def test_record_task_completed_increments_count(self):
        act = make_activity(tasks_done=1)
        act.record_task_completed()
        self.assertEqual(act.tasks_completed, 2)

    def test_contribution_score_weighting(self):
        # 1 task (3.0) + 1 file (2.0) + 10 messages (1.0) = 6.0
        act = make_activity(messages=10, files=1, tasks_done=1)
        self.assertAlmostEqual(act.contribution_score, 6.0, places=2)

if __name__ == "__main__":
    unittest.main()
