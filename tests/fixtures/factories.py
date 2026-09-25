"""
Test factories and dummy object generators.

What it does:
- Provides reusable entity factories for domain and service unit tests.
"""

from datetime import datetime, timezone, timedelta
from src.domain.entities.task import Task
from src.domain.entities.deadline import Deadline
from src.domain.entities.member_activity import MemberActivity

def make_task(
    task_id: str = "TASK-TEST01",
    guild_id: str = "guild-123",
    assigned_to: str = "user-456",
    description: str = "Sample deliverable",
    hours_from_now: int = 48,
    is_completed: bool = False,
    is_in_progress: bool = False,
    verifier_id: Optional[str] = None
) -> Task:
    now = datetime.now(timezone.utc)
    completed_at = now if is_completed else None
    return Task(
        task_id=task_id,
        guild_id=guild_id,
        channel_id="chan-789",
        message_id="msg-999",
        description=description,
        assigned_to=assigned_to,
        due_date=now + timedelta(hours=hours_from_now),
        created_at=now,
        completed_at=completed_at,
        is_in_progress=is_in_progress,
        verifier_id=verifier_id
    )

def make_deadline(
    deadline_id: str = "DL-TEST01",
    guild_id: str = "guild-123",
    name: str = "Sprint Milestone",
    hours_from_now: int = 72,
    is_completed: bool = False
) -> Deadline:
    now = datetime.now(timezone.utc)
    return Deadline(
        deadline_id=deadline_id,
        guild_id=guild_id,
        channel_id="chan-789",
        message_id="msg-999",
        name=name,
        due_datetime=now + timedelta(hours=hours_from_now),
        created_at=now,
        is_completed=is_completed
    )

def make_activity(
    guild_id: str = "guild-123",
    user_id: str = "user-456",
    messages: int = 10,
    files: int = 2,
    tasks_done: int = 3,
    on_time_tasks: int = 3,
    current_streak: int = 3,
    best_streak: int = 5
) -> MemberActivity:
    return MemberActivity(
        guild_id=guild_id,
        user_id=user_id,
        message_count=messages,
        files_submitted=files,
        tasks_completed=tasks_done,
        on_time_tasks=on_time_tasks,
        current_streak=current_streak,
        best_streak=best_streak,
        last_active=datetime.now(timezone.utc)
    )
