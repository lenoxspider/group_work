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

    def test_set_in_progress(self):
        task = make_task()
        self.assertFalse(task.is_in_progress)
        task.set_in_progress(True)
        self.assertTrue(task.is_in_progress)

    def test_is_overdue(self):
        now = datetime.now(timezone.utc)
        task_future = make_task(hours_from_now=5)
        self.assertFalse(task_future.is_overdue(now))

        task_past = make_task(hours_from_now=-2)
        self.assertTrue(task_past.is_overdue(now))

        task_completed = make_task(hours_from_now=-2, is_completed=True)
        self.assertFalse(task_completed.is_overdue(now))

    def test_needs_6h_reminder(self):
        now = datetime.now(timezone.utc)
        task = make_task(hours_from_now=5)
        self.assertTrue(task.needs_6h_reminder(now))

        task_far = make_task(hours_from_now=12)
        self.assertFalse(task_far.needs_6h_reminder(now))

    def test_extend_due_date_resets_reminders(self):
        now = datetime.now(timezone.utc)
        task = make_task(hours_from_now=2)
        task.reminded_24h = True
        task.reminded_6h = True
        task.reminded_1h = True
        task.shame_logged = True

        new_due = task.due_date + timedelta(days=3)
        task.extend_due_date(new_due)

        self.assertEqual(task.due_date, new_due)
        self.assertFalse(task.reminded_24h)
        self.assertFalse(task.reminded_6h)
        self.assertFalse(task.reminded_1h)
        self.assertFalse(task.shame_logged)

    def test_extend_due_date_earlier_raises_error(self):
        now = datetime.now(timezone.utc)
        task = make_task(hours_from_now=48)
        earlier_due = task.due_date - timedelta(hours=1)
        with self.assertRaises(ValidationError):
            task.extend_due_date(earlier_due)

    def test_assignee_cannot_be_verifier(self):
        with self.assertRaises(ValidationError):
            make_task(assigned_to="user-123", verifier_id="user-123")

    def test_task_verification_flow(self):
        task = make_task(assigned_to="user-123", verifier_id="verifier-456")
        self.assertFalse(task.is_completed)
        self.assertFalse(task.needs_verification)
        self.assertFalse(task.is_fully_verified)

        # Cannot verify before completion
        with self.assertRaises(ValidationError):
            task.verify("verifier-456")

        # Assignee completes
        task.mark_completed()
        self.assertTrue(task.is_completed)
        self.assertTrue(task.needs_verification)
        self.assertFalse(task.is_fully_verified)

        # Unauthorized user cannot verify
        with self.assertRaises(ValidationError):
            task.verify("stranger-789")

        # Designated verifier signs off
        task.verify("verifier-456")
        self.assertFalse(task.needs_verification)
        self.assertTrue(task.is_fully_verified)
        self.assertEqual(task.verified_by, "verifier-456")
        self.assertIsNotNone(task.verified_at)

        # Cannot verify again
        with self.assertRaises(ValidationError):
            task.verify("verifier-456")

if __name__ == "__main__":
    unittest.main()
