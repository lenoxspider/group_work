"""Unit tests for PreferenceService."""

import unittest
from datetime import datetime, timezone
from typing import Optional, Dict
from src.application.services.preference_service import PreferenceService
from src.application.dtos.preference_dtos import SetTimezoneDTO, SetQuietHoursDTO
from src.domain.entities.member_preference import MemberPreference
from src.domain.interfaces.preference_repository import PreferenceRepository

class InMemoryPreferenceRepository(PreferenceRepository):
    def __init__(self):
        self.store: Dict[str, MemberPreference] = {}

    def _key(self, guild_id: str, user_id: str) -> str:
        return f"{guild_id}:{user_id}"

    async def save(self, preference: MemberPreference) -> None:
        self.store[self._key(preference.guild_id, preference.user_id)] = preference

    async def get_preference(self, guild_id: str, user_id: str) -> Optional[MemberPreference]:
        return self.store.get(self._key(guild_id, user_id))

class TestPreferenceService(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.repo = InMemoryPreferenceRepository()
        self.service = PreferenceService(self.repo)

    async def test_get_preference_default(self):
        pref = await self.service.get_preference("guild-1", "user-1")
        self.assertEqual(pref.timezone_name, "UTC")
        self.assertEqual(pref.quiet_hours_start, 23)
        self.assertEqual(pref.quiet_hours_end, 8)

    async def test_set_timezone(self):
        dto = SetTimezoneDTO(guild_id="guild-1", user_id="user-1", timezone_name="America/New_York")
        result = await self.service.set_timezone(dto)
        self.assertEqual(result.timezone_name, "America/New_York")

        persisted = await self.repo.get_preference("guild-1", "user-1")
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.timezone_name, "America/New_York")

    async def test_set_quiet_hours(self):
        dto = SetQuietHoursDTO(guild_id="guild-1", user_id="user-1", start_hour=22, end_hour=7)
        result = await self.service.set_quiet_hours(dto)
        self.assertEqual(result.quiet_hours_start, 22)
        self.assertEqual(result.quiet_hours_end, 7)

        persisted = await self.repo.get_preference("guild-1", "user-1")
        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.quiet_hours_start, 22)
        self.assertEqual(persisted.quiet_hours_end, 7)

    async def test_is_in_quiet_hours(self):
        await self.service.set_quiet_hours(
            SetQuietHoursDTO(guild_id="guild-1", user_id="user-1", start_hour=23, end_hour=8)
        )
        utc_dt = datetime(2026, 9, 25, 23, 30, tzinfo=timezone.utc)
        is_quiet = await self.service.is_in_quiet_hours("guild-1", "user-1", utc_dt)
        self.assertTrue(is_quiet)

        utc_day = datetime(2026, 9, 25, 14, 0, tzinfo=timezone.utc)
        self.assertFalse(await self.service.is_in_quiet_hours("guild-1", "user-1", utc_day))

if __name__ == "__main__":
    unittest.main()
