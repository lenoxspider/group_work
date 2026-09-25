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

    def test_on_time_task_increments_streak_and_best(self):
        act = make_activity(tasks_done=2, on_time_tasks=2, current_streak=2, best_streak=2)
        act.record_task_completed(is_on_time=True)
        self.assertEqual(act.tasks_completed, 3)
        self.assertEqual(act.on_time_tasks, 3)
        self.assertEqual(act.current_streak, 3)
        self.assertEqual(act.best_streak, 3)
        self.assertEqual(act.on_time_rate, 100)

    def test_late_task_resets_current_streak_preserves_best(self):
        act = make_activity(tasks_done=2, on_time_tasks=2, current_streak=2, best_streak=5)
        act.record_task_completed(is_on_time=False)
        self.assertEqual(act.tasks_completed, 3)
        self.assertEqual(act.on_time_tasks, 2)
        self.assertEqual(act.current_streak, 0)
        self.assertEqual(act.best_streak, 5)
        self.assertEqual(act.on_time_rate, 66)

    def test_break_streak_resets_current_streak(self):
        act = make_activity(current_streak=4, best_streak=4)
        act.break_streak()
        self.assertEqual(act.current_streak, 0)
        self.assertEqual(act.best_streak, 4)

    def test_rank_title_tiers(self):
        # 0-9: Comrade
        act1 = make_activity(messages=10, files=0, tasks_done=0)  # score: 1.0
        self.assertEqual(act1.rank_title, "Comrade 🎖️")

        # 10-24: Sergeant
        act2 = make_activity(messages=0, files=0, tasks_done=4)  # score: 12.0
        self.assertEqual(act2.rank_title, "Sergeant 🎗️")

        # 25-49: Colonel
        act3 = make_activity(messages=0, files=5, tasks_done=6)  # score: 10 + 18 = 28.0
        self.assertEqual(act3.rank_title, "Colonel ⚔️")

        # 50-99: Marshal
        act4 = make_activity(messages=0, files=10, tasks_done=12)  # score: 20 + 36 = 56.0
        self.assertEqual(act4.rank_title, "Marshal 🌟")

        # 100+: General Secretary
        act5 = make_activity(messages=100, files=20, tasks_done=20)  # score: 10 + 40 + 60 = 110.0
        self.assertEqual(act5.rank_title, "General Secretary 👑")

if __name__ == "__main__":
    unittest.main()
