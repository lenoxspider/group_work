"""Community application service - onboarding, the constitution gate, intro task."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.application.dtos.task_dtos import CreateTaskDTO
from src.plugins.community.domain import CATIZEN, CITIZEN, Member, utcnow
from src.plugins.community.repository import SQLiteCommunityRepository

logger = logging.getLogger("plugins.community.service")

INTRO_TASK_DESCRIPTION = "Introduce yourself in #new-recruits"
INTRO_TASK_DUE_DAYS = 7


class CommunityService:
    def __init__(self, repo: SQLiteCommunityRepository):
        self.repo = repo
        self.bank = None
        self.task_service = None
        self.society = None

    def attach_bank(self, bank) -> None:
        self.bank = bank

    def attach_task_service(self, task_service) -> None:
        self.task_service = task_service

    def attach_society(self, society) -> None:
        self.society = society

    async def get_member(self, guild_id: str, user_id: str) -> Member:
        member = await self.repo.get_member(guild_id, user_id)
        return member or Member(guild_id=guild_id, user_id=user_id)

    async def is_citizen(self, guild_id: str, user_id: str) -> bool:
        member = await self.repo.get_member(guild_id, user_id)
        return bool(member and member.status == CITIZEN)

    async def on_join(self, guild_id: str, user_id: str) -> Optional[Member]:
        """Provision a brand-new member as a catizen and assign the intro task."""
        existing = await self.repo.get_member(guild_id, user_id)
        if existing:
            return existing  # rejoin - keep their standing

        if self.bank:
            try:
                await self.bank.ensure_account(guild_id, user_id)
            except Exception as e:
                logger.warning("Could not provision wallet for %s: %s", user_id, e)

        member = Member(guild_id=guild_id, user_id=user_id, status=CATIZEN, joined_at=utcnow())
        await self.repo.register(member)

        task = await self._assign_intro_task(guild_id, user_id)
        if task:
            member.intro_task_id = task.task_id
            await self.repo.set_intro_task(guild_id, user_id, task.task_id)
        return member

    async def _assign_intro_task(self, guild_id: str, user_id: str):
        if not self.task_service:
            return None
        due = datetime.now(timezone.utc) + timedelta(days=INTRO_TASK_DUE_DAYS)
        dto = CreateTaskDTO(
            guild_id=guild_id,
            description=INTRO_TASK_DESCRIPTION,
            assigned_to=user_id,
            due_date=due,
        )
        return await self.task_service.create_task(dto)

    async def complete_intro(self, guild_id: str, user_id: str) -> Optional[str]:
        """Credit the intro task (and its bounty) once the catizen posts their intro."""
        member = await self.repo.get_member(guild_id, user_id)
        if not member or member.intro_done or not member.intro_task_id:
            return None
        if not self.task_service:
            return None
        await self.task_service.complete_task(member.intro_task_id)
        await self.repo.mark_intro_done(guild_id, user_id)
        return member.intro_task_id

    async def sign(self, guild_id: str, user_id: str) -> Member:
        """Sign the constitution: promote a catizen to citizen (unlocks voting)."""
        now = utcnow()
        member = await self.repo.get_member(guild_id, user_id)
        if member and member.status == CITIZEN:
            return member
        if not member:
            member = Member(guild_id=guild_id, user_id=user_id, status=CITIZEN, joined_at=now, signed_at=now)
            await self.repo.register(member)
            if self.bank:
                try:
                    await self.bank.ensure_account(guild_id, user_id)
                except Exception:
                    pass
            return member
        await self.repo.sign(guild_id, user_id, now)
        member.status = CITIZEN
        member.signed_at = now
        return member

    async def enroll_existing(self, guild_id: str, user_ids, as_citizen: bool) -> int:
        """Backfill members who predate the community system. Returns count enrolled."""
        enrolled = 0
        for user_id in user_ids:
            if await self.repo.get_member(guild_id, user_id):
                continue
            if self.bank:
                try:
                    await self.bank.ensure_account(guild_id, user_id)
                except Exception:
                    pass
            now = utcnow()
            if as_citizen:
                await self.repo.register(
                    Member(guild_id=guild_id, user_id=user_id, status=CITIZEN, joined_at=now, signed_at=now)
                )
            else:
                await self.repo.register(
                    Member(guild_id=guild_id, user_id=user_id, status=CATIZEN, joined_at=now)
                )
                task = await self._assign_intro_task(guild_id, user_id)
                if task:
                    await self.repo.set_intro_task(guild_id, user_id, task.task_id)
            enrolled += 1
        return enrolled

    async def list_laws(self, guild_id: str):
        if not self.society:
            return []
        try:
            return await self.society.list_laws(guild_id)
        except Exception:
            return []