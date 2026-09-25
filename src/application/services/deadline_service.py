"""
Deadline management service.

What it does:
- Coordinates milestone scheduling, completion, and alert evaluations.
- Translates between Deadline domain aggregates and application DTOs.

What it does NOT do:
- Does NOT execute SQL statements or touch SQLite directly.
- Does NOT dispatch Discord messages or pins.
"""

import uuid
from datetime import datetime, timezone
from typing import List

from src.domain.entities.deadline import Deadline
from src.domain.errors import NotFoundError, ValidationError
from src.domain.interfaces.deadline_repository import DeadlineRepository
from src.application.dtos.deadline_dtos import (
    CreateDeadlineDTO,
    DeadlineResultDTO,
    DeadlineAlertActionDTO
)

class DeadlineService:
    """Orchestrates project deadlines and countdown alerts."""

    def __init__(self, deadline_repo: DeadlineRepository):
        self._deadline_repo = deadline_repo

    def _generate_deadline_id(self) -> str:
        return f"DL-{uuid.uuid4().hex[:6].upper()}"

    def _map_to_dto(self, dl: Deadline) -> DeadlineResultDTO:
        return DeadlineResultDTO(
            deadline_id=dl.deadline_id,
            guild_id=dl.guild_id,
            channel_id=dl.channel_id,
            message_id=dl.message_id,
            name=dl.name,
            due_datetime=dl.due_datetime,
            created_at=dl.created_at,
            is_completed=dl.is_completed
        )

    async def schedule_deadline(self, dto: CreateDeadlineDTO) -> DeadlineResultDTO:
        """Schedules and persists a new Deadline aggregate."""
        now = datetime.now(timezone.utc)
        if dto.due_datetime <= now:
            raise ValidationError("Deadline due date must be in the future.")

        deadline = Deadline(
            deadline_id=self._generate_deadline_id(),
            guild_id=dto.guild_id,
            channel_id=dto.channel_id,
            message_id=dto.message_id,
            name=dto.name,
            due_datetime=dto.due_datetime,
            created_at=now
        )
        await self._deadline_repo.save(deadline)
        return self._map_to_dto(deadline)

    async def update_message_id(self, deadline_id: str, message_id: str) -> None:
        """Attaches the Discord message ID to the deadline record."""
        dl = await self._deadline_repo.get_by_id(deadline_id)
        if not dl:
            raise NotFoundError(f"Deadline with ID {deadline_id} not found.")
        dl.message_id = message_id
        await self._deadline_repo.save(dl)

    async def complete_deadline(self, deadline_id: str) -> DeadlineResultDTO:
        """Marks a deadline as completed."""
        dl = await self._deadline_repo.get_by_id(deadline_id)
        if not dl:
            raise NotFoundError(f"Deadline with ID {deadline_id} not found.")

        dl.mark_completed()
        await self._deadline_repo.save(dl)
        return self._map_to_dto(dl)

    async def get_active_deadlines(self, guild_id: str) -> List[DeadlineResultDTO]:
        """Lists active deadlines for a guild."""
        deadlines = await self._deadline_repo.get_active_by_guild(guild_id)
        return [self._map_to_dto(d) for d in deadlines]

    async def evaluate_pending_alerts(self, current_time: datetime) -> List[DeadlineAlertActionDTO]:
        """Finds all deadlines needing 72h, 24h, or 6h alerts."""
        deadlines = await self._deadline_repo.get_all_active()
        actions: List[DeadlineAlertActionDTO] = []

        for d in deadlines:
            if d.needs_6h_alert(current_time):
                actions.append(DeadlineAlertActionDTO(
                    deadline_id=d.deadline_id,
                    guild_id=d.guild_id,
                    channel_id=d.channel_id,
                    name=d.name,
                    due_datetime=d.due_datetime,
                    alert_tier="6h"
                ))
            elif d.needs_24h_alert(current_time):
                actions.append(DeadlineAlertActionDTO(
                    deadline_id=d.deadline_id,
                    guild_id=d.guild_id,
                    channel_id=d.channel_id,
                    name=d.name,
                    due_datetime=d.due_datetime,
                    alert_tier="24h"
                ))
            elif d.needs_72h_alert(current_time):
                actions.append(DeadlineAlertActionDTO(
                    deadline_id=d.deadline_id,
                    guild_id=d.guild_id,
                    channel_id=d.channel_id,
                    name=d.name,
                    due_datetime=d.due_datetime,
                    alert_tier="72h"
                ))
        return actions

    async def acknowledge_alert(self, deadline_id: str, alert_tier: str) -> None:
        """Marks an alert tier as dispatched in repository."""
        await self._deadline_repo.update_reminder(deadline_id, alert_tier)
