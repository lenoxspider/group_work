"""Unit tests for Deadline entity."""

import unittest
from datetime import datetime, timezone, timedelta
from src.domain.errors import ValidationError, DeadlineAlreadyCompletedError
from tests.fixtures.factories import make_deadline

class TestDeadlineEntity(unittest.TestCase):

    def test_deadline_creation_valid(self):
        dl = make_deadline(name="Final Report")
        self.assertEqual(dl.name, "Final Report")
        self.assertFalse(dl.is_completed)

    def test_deadline_empty_name_raises_error(self):
        with self.assertRaises(ValidationError):
            make_deadline(name="   ")

    def test_mark_completed_sets_flag(self):
        dl = make_deadline()
        dl.mark_completed()
        self.assertTrue(dl.is_completed)

    def test_mark_completed_twice_raises_error(self):
        dl = make_deadline()
        dl.mark_completed()
        with self.assertRaises(DeadlineAlreadyCompletedError):
            dl.mark_completed()

    def test_time_remaining_calculation(self):
        now = datetime.now(timezone.utc)
        dl = make_deadline(hours_from_now=50)
        days, hours, minutes, is_overdue = dl.get_time_remaining(now)
        self.assertFalse(is_overdue)
        self.assertEqual(days, 2)
        self.assertEqual(hours, 2)

    def test_time_remaining_when_overdue(self):
        now = datetime.now(timezone.utc)
        dl = make_deadline(hours_from_now=-5)
        _, _, _, is_overdue = dl.get_time_remaining(now)
        self.assertTrue(is_overdue)

    def test_needs_72h_alert(self):
        now = datetime.now(timezone.utc)
        dl = make_deadline(hours_from_now=48)
        self.assertTrue(dl.needs_72h_alert(now))

    def test_needs_24h_alert(self):
        now = datetime.now(timezone.utc)
        dl = make_deadline(hours_from_now=12)
        self.assertTrue(dl.needs_24h_alert(now))

    def test_needs_6h_alert(self):
        now = datetime.now(timezone.utc)
        dl = make_deadline(hours_from_now=3)
        self.assertTrue(dl.needs_6h_alert(now))

if __name__ == "__main__":
    unittest.main()
