"""
Alert fire repository interface.

What it does:
- Defines abstract contract for tracking idempotent alert triggers across system restarts.

What it does NOT do:
- Does NOT execute SQL statements or import concrete database drivers.
"""

from typing import Protocol, List
from src.domain.entities.alert_fire import AlertFire

class AlertFireRepository(Protocol):
    """Abstract persistence interface for tracking fired alert tiers."""

    async def record_fire(self, alert_fire: AlertFire) -> bool:
        """
        Attempts to atomically record an alert fire.
        Returns True if newly recorded, or False if this alert tier already fired for the task.
        """
        ...

    async def has_fired(self, task_id: int, alert_tier: str) -> bool:
        """Checks if a specific tier has already fired for a task."""
        ...

    async def list_fired_tiers(self, task_id: int) -> List[str]:
        """Lists all alert tiers that have already fired for a task."""
        ...
