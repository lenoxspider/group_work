"""
Member preference application service.

What it does:
- Manages student timezone settings and notification quiet hours.
- Evaluates whether a user is currently within their quiet hours.

What it does NOT do:
- Does NOT execute SQL statements directly.
- Does NOT send Discord messages.
"""

from datetime import datetime, timezone
from typing import Optional
from src.domain.entities.member_preference import MemberPreference
from src.domain.interfaces.preference_repository import PreferenceRepository
from src.application.dtos.preference_dtos import (
    SetTimezoneDTO,
    SetQuietHoursDTO,
    MemberPreferenceDTO
)

class PreferenceService:
    """Orchestrates member notification and timezone preferences."""

    def __init__(self, preference_repo: PreferenceRepository):
        self.repo = preference_repo

    def _to_dto(self, pref: MemberPreference, now: Optional[datetime] = None) -> MemberPreferenceDTO:
        check_time = now or datetime.now(timezone.utc)
        return MemberPreferenceDTO(
            guild_id=pref.guild_id,
            user_id=pref.user_id,
            timezone_name=pref.timezone_name,
            quiet_hours_start=pref.quiet_hours_start,
            quiet_hours_end=pref.quiet_hours_end,
            is_currently_quiet=pref.is_in_quiet_hours(check_time)
        )

    async def get_preference(self, guild_id: str, user_id: str) -> MemberPreferenceDTO:
        """Retrieves member preference or returns standard UTC default."""
        pref = await self.repo.get_preference(guild_id, user_id)
        if not pref:
            pref = MemberPreference(guild_id=guild_id, user_id=user_id)
        return self._to_dto(pref)

    async def set_timezone(self, dto: SetTimezoneDTO) -> MemberPreferenceDTO:
        """Updates and persists member's IANA timezone."""
        pref = await self.repo.get_preference(dto.guild_id, dto.user_id)
        now = datetime.now(timezone.utc)
        if pref:
            pref.timezone_name = dto.timezone_name
            pref.updated_at = now
        else:
            pref = MemberPreference(
                guild_id=dto.guild_id,
                user_id=dto.user_id,
                timezone_name=dto.timezone_name,
                updated_at=now
            )
        await self.repo.save(pref)
        return self._to_dto(pref, now)

    async def set_quiet_hours(self, dto: SetQuietHoursDTO) -> MemberPreferenceDTO:
        """Updates and persists member's quiet hours (DND) window."""
        pref = await self.repo.get_preference(dto.guild_id, dto.user_id)
        now = datetime.now(timezone.utc)
        if pref:
            pref.quiet_hours_start = dto.start_hour
            pref.quiet_hours_end = dto.end_hour
            pref.updated_at = now
        else:
            pref = MemberPreference(
                guild_id=dto.guild_id,
                user_id=dto.user_id,
                quiet_hours_start=dto.start_hour,
                quiet_hours_end=dto.end_hour,
                updated_at=now
            )
        await self.repo.save(pref)
        return self._to_dto(pref, now)

    async def is_in_quiet_hours(self, guild_id: str, user_id: str, utc_now: datetime) -> bool:
        """Checks if a member is currently in their designated quiet hours window."""
        pref = await self.repo.get_preference(guild_id, user_id)
        if not pref:
            return False
        return pref.is_in_quiet_hours(utc_now)
