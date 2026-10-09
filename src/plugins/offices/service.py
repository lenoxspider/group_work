"""Offices service - who holds which office.

Appointments are recorded in the chronicle, because an office changing hands is
exactly the kind of moment the state should remember.
"""

import logging
from datetime import datetime, timezone
from typing import List, Optional

from src.plugins.offices.domain import OFFICES, OFFICE_LABELS
from src.plugins.offices.repository import SQLiteOfficesRepository

logger = logging.getLogger("plugins.offices.service")


class OfficeError(Exception):
    """A refusal that is safe to show the caller."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class OfficesService:
    def __init__(self, repo: SQLiteOfficesRepository):
        self.repo = repo
        self.chronicle = None

    def attach_chronicle(self, chronicle) -> None:
        self.chronicle = chronicle

    @staticmethod
    def is_valid(office: str) -> bool:
        return office in OFFICES

    async def appoint(self, guild_id, office, user_id, appointed_by=None) -> Optional[str]:
        """Set the holder of an office, returning whoever it vacated (if anyone)."""
        if office not in OFFICES:
            raise OfficeError(f"Unknown office '{office}'.")
        previous = await self.repo.holder(guild_id, office)
        await self.repo.set_holder(guild_id, office, user_id, _now(), appointed_by)
        if self.chronicle:
            label = OFFICE_LABELS.get(office, office)
            await self.chronicle.record(
                guild_id, "office_appointed", f"🎖️ <@{user_id}> was appointed {label}."
            )
        return previous

    async def vacate(self, guild_id, office) -> Optional[str]:
        if office not in OFFICES:
            raise OfficeError(f"Unknown office '{office}'.")
        previous = await self.repo.holder(guild_id, office)
        await self.repo.clear_office(guild_id, office)
        if previous and self.chronicle:
            label = OFFICE_LABELS.get(office, office)
            await self.chronicle.record(
                guild_id, "office_vacated", f"🎖️ The office of {label} was vacated by <@{previous}>."
            )
        return previous

    async def holder(self, guild_id, office) -> Optional[str]:
        return await self.repo.holder(guild_id, office)

    async def holds(self, guild_id, user_id, office) -> bool:
        return await self.repo.holder(guild_id, office) == user_id

    async def offices_held_by(self, guild_id, user_id) -> List[str]:
        return await self.repo.offices_held_by(guild_id, user_id)

    async def all_offices(self, guild_id) -> List[dict]:
        return await self.repo.all_offices(guild_id)
