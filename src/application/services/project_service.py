"""
Project lifecycle service.

What it does:
- Coordinates project progress status and project archiving.
- Compiles retrospective summary metrics upon project completion.

What it does NOT do:
- Does NOT interact with Discord channels or adjust Discord permissions directly.
- Does NOT execute raw SQL queries.
"""

from datetime import datetime, timezone
from typing import Optional, List

from src.domain.entities.project_state import ProjectState, ProjectStatus
from src.domain.interfaces.project_repository import ProjectRepository
from src.domain.interfaces.task_repository import TaskRepository
from src.domain.interfaces.deadline_repository import DeadlineRepository
from src.domain.interfaces.activity_repository import ActivityRepository
from src.application.dtos.project_dtos import ProjectStatusDTO, ProjectArchiveSummaryDTO
from src.application.dtos.report_dtos import GuildStandingItemDTO

class ProjectService:
    """Orchestrates project lifecycle, health dashboards, and retrospective archiving."""

    def __init__(
        self,
        project_repo: ProjectRepository,
        task_repo: TaskRepository,
        deadline_repo: DeadlineRepository,
        activity_repo: ActivityRepository
    ):
        self._project_repo = project_repo
        self._task_repo = task_repo
        self._deadline_repo = deadline_repo
        self._activity_repo = activity_repo

    async def get_project_status(self, guild_id: str) -> ProjectStatusDTO:
        """Retrieves real-time dashboard metrics for the project."""
        state = await self._project_repo.get_state(guild_id)
        current_status = state.status.value if state else ProjectStatus.ACTIVE.value

        pending_tasks = await self._task_repo.get_pending_by_guild(guild_id)
        active_deadlines = await self._deadline_repo.get_active_by_guild(guild_id)
        standings = await self._activity_repo.get_guild_standings(guild_id)

        completed_tasks_count = sum(s.tasks_completed for s in standings)
        files_submitted_count = sum(s.files_submitted for s in standings)
        total_tasks = completed_tasks_count + len(pending_tasks)

        nearest_name = None
        nearest_due = None
        if active_deadlines:
            nearest = active_deadlines[0]
            nearest_name = nearest.name
            nearest_due = nearest.due_datetime

        return ProjectStatusDTO(
            guild_id=guild_id,
            status=current_status,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks_count,
            pending_tasks=len(pending_tasks),
            active_deadlines_count=len(active_deadlines),
            nearest_deadline_name=nearest_name,
            nearest_deadline_due=nearest_due,
            total_files_submitted=files_submitted_count
        )

    async def archive_project(self, guild_id: str, archived_by_user_id: str) -> ProjectArchiveSummaryDTO:
        """Transitions project to archived state and produces retrospective summary."""
        state = await self._project_repo.get_state(guild_id)
        if not state:
            state = ProjectState(guild_id=guild_id)

        now = datetime.now(timezone.utc)
        state.archive(archived_by_user_id, timestamp=now)
        await self._project_repo.save_state(state)

        standings_entities = await self._activity_repo.get_guild_standings(guild_id)
        standings_dtos: List[GuildStandingItemDTO] = [
            GuildStandingItemDTO(
                user_id=s.user_id,
                message_count=s.message_count,
                files_submitted=s.files_submitted,
                tasks_completed=s.tasks_completed,
                contribution_score=s.contribution_score,
                on_time_rate=s.on_time_rate,
                current_streak=s.current_streak,
                rank_title=s.rank_title
            )
            for s in standings_entities
        ]

        total_tasks_completed = sum(s.tasks_completed for s in standings_dtos)
        total_files = sum(s.files_submitted for s in standings_dtos)

        return ProjectArchiveSummaryDTO(
            guild_id=guild_id,
            archived_at=now,
            archived_by=archived_by_user_id,
            total_tasks_completed=total_tasks_completed,
            total_files_submitted=total_files,
            standings=standings_dtos
        )
