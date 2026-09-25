"""Unit tests for Task entity."""

import unittest
from datetime import datetime, timezone, timedelta
from src.domain.errors import ValidationError, TaskAlreadyCompletedError
from tests.fixtures.factories import make_task

class TestTaskEntity(unittest.TestCase):

    def test_task_creation_valid(self):
        task = make_task(task_id="TASK-01", description="Draft section 1")
        self.assertEqual(task.task_id, "TASK-01")
        self.assertFalse(task.is_completed)

    def test_task_empty_description_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            make_task(description="  ")

    def test_mark_completed_sets_completed_at(self):
        task = make_task()
        task.mark_completed()
        self.assertTrue(task.is_completed)
        self.assertIsNotNone(task.completed_at)

    def test_mark_completed_twice_raises_error(self):
        task = make_task()
        task.mark_completed()
        with self.assertRaises(TaskAlreadyCompletedError):
            task.mark_completed()

    def test_needs_24h_reminder_when_due_in_20_hours(self):
        now = datetime.now(timezone.utc)
        task = make_task(hours_from_now=20)
        self.assertTrue(task.needs_24h_reminder(now))

    def test_does_not_need_24h_reminder_when_already_reminded(self):
        now = datetime.now(timezone.utc)
        task = make_task(hours_from_now=20)
        task.reminded_24h = True
        self.assertFalse(task.needs_24h_reminder(now))

    def test_needs_1h_reminder_when_due_in_30_minutes(self):
        now = datetime.now(timezone.utc)
        task = make_task(hours_from_now=1)
        task.due_date = now + timedelta(minutes=30)
        self.assertTrue(task.needs_1h_reminder(now))

if __name__ == "__main__":
    unittest.main()
