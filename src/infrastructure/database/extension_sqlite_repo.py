"""
SQLite implementation of ExtensionRepository.

What it does:
- Persists and retrieves ExtensionRequest aggregates in SQLite.
- Serializes approvals and rejections sets to comma-separated strings.

What it does NOT do:
- Does NOT execute business rules or voting resolution logic.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import aiosqlite

from src.domain.entities.extension_request import ExtensionRequest
from src.domain.interfaces.extension_repository import ExtensionRepository

class SQLiteExtensionRepository(ExtensionRepository):
    """aiosqlite-backed repository for ExtensionRequest aggregates."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _row_to_entity(self, row: Dict[str, Any]) -> ExtensionRequest:
        approvals = set(filter(None, row["approvals"].split(","))) if row.get("approvals") else set()
        rejections = set(filter(None, row["rejections"].split(","))) if row.get("rejections") else set()
        resolved_at = datetime.fromisoformat(row["resolved_at"]) if row.get("resolved_at") else None

        return ExtensionRequest(
            request_id=row["request_id"],
            task_id=row["task_id"],
            guild_id=row["guild_id"],
            requester_id=row["requester_id"],
            proposed_due_date=datetime.fromisoformat(row["proposed_due_date"]),
            reason=row["reason"],
            created_at=datetime.fromisoformat(row["created_at"]),
            status=row["status"],
            approvals=approvals,
            rejections=rejections,
            resolved_at=resolved_at
        )

    async def save(self, extension: ExtensionRequest) -> None:
        approvals_str = ",".join(sorted(extension.approvals))
        rejections_str = ",".join(sorted(extension.rejections))
        resolved_str = extension.resolved_at.isoformat() if extension.resolved_at else None

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO extension_requests (
                    request_id, task_id, guild_id, requester_id,
                    proposed_due_date, reason, status, approvals,
                    rejections, created_at, resolved_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(request_id) DO UPDATE SET
                    status = excluded.status,
                    approvals = excluded.approvals,
                    rejections = excluded.rejections,
                    resolved_at = excluded.resolved_at
            """, (
                extension.request_id, extension.task_id, extension.guild_id,
                extension.requester_id, extension.proposed_due_date.isoformat(),
                extension.reason, extension.status, approvals_str,
                rejections_str, extension.created_at.isoformat(), resolved_str
            ))
            await db.commit()

    async def get_by_id(self, request_id: str) -> Optional[ExtensionRequest]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM extension_requests WHERE request_id = ?",
                (request_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._row_to_entity(dict(row)) if row else None

    async def get_pending_by_task(self, task_id: str) -> Optional[ExtensionRequest]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM extension_requests WHERE task_id = ? AND status = 'PENDING'",
                (task_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._row_to_entity(dict(row)) if row else None

    async def get_pending_by_guild(self, guild_id: str) -> List[ExtensionRequest]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM extension_requests WHERE guild_id = ? AND status = 'PENDING' ORDER BY created_at ASC",
                (guild_id,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_entity(dict(r)) for r in rows]
