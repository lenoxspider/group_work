"""Unit tests for MemberPreference aggregate entity."""

import unittest
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from src.domain.entities.member_preference import MemberPreference
from src.domain.errors import ValidationError

class TestMemberPreferenceEntity(unittest.TestCase):

    def test_default_preference(self):
        pref = MemberPreference(guild_id="guild-1", user_id="user-1")
        self.assertEqual(pref.timezone_name, "UTC")
        self.assertEqual(pref.quiet_hours_start, 23)
        self.assertEqual(pref.quiet_hours_end, 8)

    def test_empty_ids_raise_validation_error(self):
        with self.assertRaises(ValidationError):
            MemberPreference(guild_id="  ", user_id="user-1")
        with self.assertRaises(ValidationError):
            MemberPreference(guild_id="guild-1", user_id=" ")

    def test_invalid_timezone_raises_validation_error(self):
        with self.assertRaises(ValidationError):
            MemberPreference(guild_id="guild-1", user_id="user-1", timezone_name="Mars/Olympus")

    def test_invalid_quiet_hours_raise_validation_error(self):
        with self.assertRaises(ValidationError):
            MemberPreference(guild_id="guild-1", user_id="user-1", quiet_hours_start=24)
        with self.assertRaises(ValidationError):
            MemberPreference(guild_id="guild-1", user_id="user-1", quiet_hours_end=-1)

    def test_quiet_hours_crosses_midnight(self):
        # 23:00 to 08:00 UTC
        pref = MemberPreference(guild_id="guild-1", user_id="user-1", timezone_name="UTC", quiet_hours_start=23, quiet_hours_end=8)

        # 23:30 UTC -> inside
        dt1 = datetime(2026, 9, 25, 23, 30, tzinfo=timezone.utc)
        self.assertTrue(pref.is_in_quiet_hours(dt1))

        # 04:00 UTC -> inside
        dt2 = datetime(2026, 9, 25, 4, 0, tzinfo=timezone.utc)
        self.assertTrue(pref.is_in_quiet_hours(dt2))

        # 08:00 UTC -> outside
        dt3 = datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
        self.assertFalse(pref.is_in_quiet_hours(dt3))

        # 14:00 UTC -> outside
        dt4 = datetime(2026, 9, 25, 14, 0, tzinfo=timezone.utc)
        self.assertFalse(pref.is_in_quiet_hours(dt4))

    def test_quiet_hours_same_day(self):
        # 02:00 to 06:00 UTC
        pref = MemberPreference(guild_id="guild-1", user_id="user-1", timezone_name="UTC", quiet_hours_start=2, quiet_hours_end=6)

        dt_in = datetime(2026, 9, 25, 3, 30, tzinfo=timezone.utc)
        self.assertTrue(pref.is_in_quiet_hours(dt_in))

        dt_out = datetime(2026, 9, 25, 7, 0, tzinfo=timezone.utc)
        self.assertFalse(pref.is_in_quiet_hours(dt_out))

    def test_quiet_hours_disabled_when_equal(self):
        pref = MemberPreference(guild_id="guild-1", user_id="user-1", quiet_hours_start=0, quiet_hours_end=0)
        dt = datetime(2026, 9, 25, 0, 0, tzinfo=timezone.utc)
        self.assertFalse(pref.is_in_quiet_hours(dt))

    def test_timezone_conversion(self):
        # User in America/New_York (UTC-4 in daylight savings)
        # Quiet hours: 22:00 to 07:00 local time
        pref = MemberPreference(
            guild_id="guild-1",
            user_id="user-1",
            timezone_name="America/New_York",
            quiet_hours_start=22,
            quiet_hours_end=7
        )

        # 03:00 UTC is 23:00 in New York (EDT, UTC-4) -> Should be inside quiet hours
        utc_dt = datetime(2026, 9, 25, 3, 0, tzinfo=timezone.utc)
        self.assertTrue(pref.is_in_quiet_hours(utc_dt))

        # 16:00 UTC is 12:00 (noon) in New York -> Should be outside quiet hours
        utc_dt_noon = datetime(2026, 9, 25, 16, 0, tzinfo=timezone.utc)
        self.assertFalse(pref.is_in_quiet_hours(utc_dt_noon))

if __name__ == "__main__":
    unittest.main()
