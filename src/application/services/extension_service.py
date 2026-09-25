"""
Extension request application service.

What it does:
- Orchestrates creation, voting, and resolution of task extension requests.
- Applies approved deadline extensions to the underlying Task aggregate.

What it does NOT do:
- Does NOT execute direct SQL queries.
- Does NOT directly send Discord messages or interact with Discord gateway.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from src.domain.entities.extension_request import ExtensionRequest
from src.domain.interfaces.extension_repository import ExtensionRepository
from src.domain.interfaces.task_repository import TaskRepository
from src.domain.errors import NotFoundError, ValidationError
from src.application.dtos.extension_dtos import (
    CreateExtensionDTO,
    CastVoteDTO,
    ExtensionResultDTO
)

class ExtensionService:
    """Orchestrates task extension requests and democratic peer voting."""

    def __init__(self, extension_repo: ExtensionRepository, task_repo: TaskRepository):
        self.extension_repo = extension_repo
        self.task_repo = task_repo

    def _to_dto(self, entity: ExtensionRequest) -> ExtensionResultDTO:
        return ExtensionResultDTO(
            request_id=entity.request_id,
            task_id=entity.task_id,
            guild_id=entity.guild_id,
            requester_id=entity.requester_id,
            proposed_due_date=entity.proposed_due_date,
            reason=entity.reason,
            status=entity.status,
            approvals_count=len(entity.approvals),
            rejections_count=len(entity.rejections),
            approvals=set(entity.approvals),
            rejections=set(entity.rejections),
            created_at=entity.created_at,
            resolved_at=entity.resolved_at
        )

    async def request_extension(self, dto: CreateExtensionDTO) -> ExtensionResultDTO:
        """Submits a new formal extension request for team voting."""
        task = await self.task_repo.get_by_id(dto.task_id)
        if not task:
            raise NotFoundError(f"Task with ID {dto.task_id} not found.")
        if task.is_completed:
            raise ValidationError(f"Cannot request an extension on completed task {dto.task_id}.")
        if str(dto.requester_id) != str(task.assigned_to):
            raise ValidationError("Only the assigned member can request a deadline extension.")
        if dto.proposed_due_date <= task.due_date:
            raise ValidationError("Proposed new due date must be strictly after the current deadline.")

        existing = await self.extension_repo.get_pending_by_task(dto.task_id)
        if existing:
            raise ValidationError(f"An active extension vote ({existing.request_id}) is already pending for this task.")

        req_id = f"EXT-{uuid.uuid4().hex[:8].upper()}"
        now = datetime.now(timezone.utc)
        extension = ExtensionRequest(
            request_id=req_id,
            task_id=dto.task_id,
            guild_id=dto.guild_id,
            requester_id=dto.requester_id,
            proposed_due_date=dto.proposed_due_date,
            reason=dto.reason,
            created_at=now
        )
        await self.extension_repo.save(extension)
        return self._to_dto(extension)

    async def cast_vote(self, dto: CastVoteDTO) -> ExtensionResultDTO:
        """Casts or changes a teammate's vote on an active extension request."""
        extension = await self.extension_repo.get_by_id(dto.request_id)
        if not extension:
            raise NotFoundError(f"Extension request {dto.request_id} not found.")

        extension.cast_vote(dto.user_id, dto.approve)
        await self.extension_repo.save(extension)
        return self._to_dto(extension)

    async def conclude_vote(self, request_id: str, resolved_by_user_id: str) -> ExtensionResultDTO:
        """
        Concludes voting and applies the outcome based on the majority of votes cast.
        """
        extension = await self.extension_repo.get_by_id(request_id)
        if not extension:
            raise NotFoundError(f"Extension request {request_id} not found.")

        approved = extension.resolve_majority()
        if approved:
            task = await self.task_repo.get_by_id(extension.task_id)
            if task:
                task.extend_due_date(extension.proposed_due_date)
                await self.task_repo.update_due_date(task.task_id, extension.proposed_due_date)

        await self.extension_repo.save(extension)
        return self._to_dto(extension)

    async def get_extension(self, request_id: str) -> ExtensionResultDTO:
        """Retrieves state of a single extension request."""
        extension = await self.extension_repo.get_by_id(request_id)
        if not extension:
            raise NotFoundError(f"Extension request {request_id} not found.")
        return self._to_dto(extension)
