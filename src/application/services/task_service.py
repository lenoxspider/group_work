"""
Task management service.

What it does:
- Coordinates task creation, status transitions, and reminder evaluations.
- Translates between Task domain aggregates and application DTOs.

What it does NOT do:
- Does NOT construct raw SQL or access database drivers directly.
- Does NOT send Discord messages or interact with Discord gateway.
"""

import uuid
from datetime import datetime, timezone
from typing import List, Optional

from src.domain.entities.task import Task
from src.domain.errors import NotFoundError, ValidationError
from src.domain.interfaces.task_repository import TaskRepository
from src.domain.interfaces.activity_repository import ActivityRepository
from src.application.dtos.task_dtos import (
    CreateTaskDTO,
    TaskResultDTO,
    TaskReminderActionDTO,
    OverdueShameActionDTO
)

class TaskService:
    """Orchestrates task assignments, completions, and reminders."""

    def __init__(self, task_repo: TaskRepository, activity_repo: ActivityRepository):
        self._task_repo = task_repo
        self._activity_repo = activity_repo

    def _generate_task_id(self) -> str:
        return f"TASK-{uuid.uuid4().hex[:6].upper()}"

    def _map_to_dto(self, task: Task) -> TaskResultDTO:
        return TaskResultDTO(
            task_id=task.task_id,
            guild_id=task.guild_id,
            channel_id=task.channel_id,
            message_id=task.message_id,
            description=task.description,
            assigned_to=task.assigned_to,
            due_date=task.due_date,
            created_at=task.created_at,
            completed_at=task.completed_at,
            is_completed=task.is_completed,
            is_in_progress=task.is_in_progress,
            is_on_time=task.is_on_time,
            verifier_id=task.verifier_id,
            verified_at=task.verified_at,
            verified_by=task.verified_by,
            needs_verification=task.needs_verification,
            is_fully_verified=task.is_fully_verified
        )

    async def create_task(self, dto: CreateTaskDTO) -> TaskResultDTO:
        """Creates and stores a new Task aggregate with optional accountability buddy."""
        now = datetime.now(timezone.utc)
        if dto.due_date <= now:
            raise ValidationError("Task due date must be in the future.")

        task = Task(
            task_id=self._generate_task_id(),
            guild_id=dto.guild_id,
            channel_id=dto.channel_id,
            message_id=dto.message_id,
            description=dto.description,
            assigned_to=dto.assigned_to,
            due_date=dto.due_date,
            created_at=now,
            verifier_id=dto.verifier_id
        )
        await self._task_repo.save(task)
        return self._map_to_dto(task)

    async def update_task_message_id(self, task_id: str, message_id: str) -> None:
        """Attaches the Discord message ID to the task record."""
        task = await self._task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with ID {task_id} not found.")
        task.message_id = message_id
        await self._task_repo.save(task)

    async def complete_task(self, task_id: str) -> TaskResultDTO:
        """Marks a task completed. If no verifier assigned, credits points immediately."""
        task = await self._task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with ID {task_id} not found.")

        task.mark_completed()
        is_on_time = bool(task.is_on_time)
        await self._task_repo.save(task)

        # If no buddy verification required, award activity score & streak immediately
        if not task.verifier_id:
            await self._activity_repo.record_task_completed(task.guild_id, task.assigned_to, is_on_time=is_on_time)
        return self._map_to_dto(task)

    async def verify_task(self, task_id: str, verifier_user_id: str) -> TaskResultDTO:
        """Signs off on a completed task as accountability buddy, crediting both members."""
        task = await self._task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with ID {task_id} not found.")

        task.verify(verifier_user_id)
        is_on_time = bool(task.is_on_time)
        await self._task_repo.save(task)

        # Credit assignee's task completion and streak
        await self._activity_repo.record_task_completed(task.guild_id, task.assigned_to, is_on_time=is_on_time)
        # Award buddy verification bonus to the verifier
        await self._activity_repo.record_file_submission(task.guild_id, verifier_user_id)
        return self._map_to_dto(task)

    async def toggle_in_progress(self, task_id: str) -> TaskResultDTO:
        """Toggles the in-progress status of an open task."""
        task = await self._task_repo.get_by_id(task_id)
        if not task:
            raise NotFoundError(f"Task with ID {task_id} not found.")

        task.set_in_progress(not task.is_in_progress)
        await self._task_repo.update_progress(task_id, task.is_in_progress)
        return self._map_to_dto(task)

    async def evaluate_overdue_tasks(self, current_time: datetime) -> List[OverdueShameActionDTO]:
        """Finds open tasks past due date and breaks user streaks."""
        overdue_tasks = await self._task_repo.get_overdue_unshamed(current_time)
        actions: List[OverdueShameActionDTO] = []

        for task in overdue_tasks:
            # Break on-time streak
            await self._activity_repo.reset_streak(task.guild_id, task.assigned_to)
            hours_diff = max(1, int((current_time - task.due_date).total_seconds() // 3600))
            actions.append(OverdueShameActionDTO(
                task_id=task.task_id,
                guild_id=task.guild_id,
                user_id=task.assigned_to,
                description=task.description,
                due_date=task.due_date,
                hours_overdue=hours_diff
            ))
        return actions

    async def acknowledge_shame(self, task_id: str) -> None:
        """Marks task as logged to Wall of Shame."""
        await self._task_repo.mark_shame_logged(task_id)

    async def get_pending_tasks(self, guild_id: str, member_id: Optional[str] = None) -> List[TaskResultDTO]:
        """Lists pending tasks for a guild, optionally filtered by member."""
        tasks = await self._task_repo.get_pending_by_guild(guild_id)
        if member_id:
            tasks = [t for t in tasks if t.assigned_to == member_id]
        return [self._map_to_dto(t) for t in tasks]

    async def evaluate_pending_reminders(self, current_time: datetime) -> List[TaskReminderActionDTO]:
        """Finds all tasks needing 24h, 6h, or 1h escalating reminders."""
        tasks = await self._task_repo.get_all_pending()
        actions: List[TaskReminderActionDTO] = []

        for task in tasks:
            if task.needs_1h_reminder(current_time):
                actions.append(TaskReminderActionDTO(
                    task_id=task.task_id,
                    guild_id=task.guild_id,
                    user_id=task.assigned_to,
                    description=task.description,
                    due_date=task.due_date,
                    reminder_tier="1h"
                ))
            elif task.needs_6h_reminder(current_time):
                actions.append(TaskReminderActionDTO(
                    task_id=task.task_id,
                    guild_id=task.guild_id,
                    user_id=task.assigned_to,
                    description=task.description,
                    due_date=task.due_date,
                    reminder_tier="6h"
                ))
            elif task.needs_24h_reminder(current_time):
                actions.append(TaskReminderActionDTO(
                    task_id=task.task_id,
                    guild_id=task.guild_id,
                    user_id=task.assigned_to,
                    description=task.description,
                    due_date=task.due_date,
                    reminder_tier="24h"
                ))
        return actions

    async def acknowledge_reminder(self, task_id: str, reminder_tier: str) -> None:
        """Marks a reminder tier as dispatched in repository."""
        await self._task_repo.update_reminder(task_id, reminder_tier)
