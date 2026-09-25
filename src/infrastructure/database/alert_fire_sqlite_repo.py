"""
SQLite implementation of AlertFireRepository.

What it does:
- Atomically records and checks fired alert tiers for tasks, preventing duplicate alerts across restarts.

What it does NOT do:
- Does NOT execute discord notifications or business orchestration.
"""

from typing import List
import aiosqlite
from src.domain.entities.alert_fire import AlertFire
from src.domain.interfaces.alert_fire_repository import AlertFireRepository

class SQLiteAlertFireRepository(AlertFireRepository):
    """aiosqlite-backed repository for idempotent alert notification tracking."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def record_fire(self, alert_fire: AlertFire) -> bool:
        """
        Attempts to atomically record an alert fire using INSERT OR IGNORE.
        Returns True if newly recorded (first time), False if duplicate (already fired).
        """
        query = """
            INSERT OR IGNORE INTO alert_fires (task_id, alert_tier, fired_at)
            VALUES (?, ?, ?)
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                query,
                (alert_fire.task_id, alert_fire.alert_tier, alert_fire.fired_at.isoformat())
            )
            await db.commit()
            return cursor.rowcount > 0

    async def has_fired(self, task_id: int, alert_tier: str) -> bool:
        """Checks if a specific tier has already fired for a task."""
        query = "SELECT 1 FROM alert_fires WHERE task_id = ? AND alert_tier = ?"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, (task_id, alert_tier)) as cursor:
                row = await cursor.fetchone()
                return row is not None

    async def list_fired_tiers(self, task_id: int) -> List[str]:
        """Lists all alert tiers that have already fired for a task."""
        query = "SELECT alert_tier FROM alert_fires WHERE task_id = ?"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, (task_id,)) as cursor:
                rows = await cursor.fetchall()
                return [row[0] for row in rows]
