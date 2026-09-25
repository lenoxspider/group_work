"""
Member activity and contribution reporting service.

What it does:
- Records message volume and task completions.
- Compiles individual student scorecards and team contribution standings.

What it does NOT do:
- Does NOT parse Discord message events directly.
- Does NOT execute raw SQL queries.
"""

from typing import Optional
from src.domain.interfaces.activity_repository import ActivityRepository
from src.domain.interfaces.task_repository import TaskRepository
from src.application.dtos.report_dtos import (
    MemberReportDTO,
    GuildStandingItemDTO,
    GuildReportDTO
)

class ActivityService:
    """Orchestrates anti-free-riding metrics and report generation."""

    def __init__(self, activity_repo: ActivityRepository, task_repo: TaskRepository):
        self._activity_repo = activity_repo
        self._task_repo = task_repo

    async def record_message(self, guild_id: str, user_id: str) -> None:
        """Increments member message counter."""
        await self._activity_repo.record_message(guild_id, user_id)

    async def get_member_report(self, guild_id: str, user_id: str) -> MemberReportDTO:
        """Compiles detailed individual accountability report."""
        activity = await self._activity_repo.get_activity(guild_id, user_id)
        pending_tasks = await self._task_repo.get_pending_by_guild(guild_id)
        user_pending_count = sum(1 for t in pending_tasks if t.assigned_to == user_id)

        msg_count = activity.message_count if activity else 0
        files_count = activity.files_submitted if activity else 0
        tasks_done = activity.tasks_completed if activity else 0
        score = activity.contribution_score if activity else 0.0
        last_active = activity.last_active if activity else None

        total_tasks = tasks_done + user_pending_count
        completion_rate = int((tasks_done / total_tasks) * 100) if total_tasks > 0 else 0

        on_time_rate = activity.on_time_rate if activity else 100
        current_streak = activity.current_streak if activity else 0
        best_streak = activity.best_streak if activity else 0
        rank_title = activity.rank_title if activity else "Comrade 🎖️"

        return MemberReportDTO(
            guild_id=guild_id,
            user_id=user_id,
            message_count=msg_count,
            files_submitted=files_count,
            tasks_completed=tasks_done,
            pending_tasks=user_pending_count,
            completion_rate=completion_rate,
            on_time_rate=on_time_rate,
            current_streak=current_streak,
            best_streak=best_streak,
            rank_title=rank_title,
            contribution_score=score,
            last_active=last_active
        )

    async def get_guild_report(self, guild_id: str) -> GuildReportDTO:
        """Compiles group-wide contribution leaderboard."""
        standings = await self._activity_repo.get_guild_standings(guild_id)
        items = [
            GuildStandingItemDTO(
                user_id=s.user_id,
                message_count=s.message_count,
                files_submitted=s.files_submitted,
                tasks_completed=s.tasks_completed,
                on_time_rate=s.on_time_rate,
                current_streak=s.current_streak,
                rank_title=s.rank_title,
                contribution_score=s.contribution_score
            )
            for s in standings
        ]
        return GuildReportDTO(guild_id=guild_id, standings=items)
