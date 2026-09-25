"""
SQLite implementation of ProjectRepository.

What it does:
- Persists and loads ProjectState aggregates for Discord guilds.

What it does NOT do:
- Does NOT execute business rules or interact with Discord APIs.
"""

from datetime import datetime
from typing import Optional, Dict, Any
import aiosqlite

from src.domain.entities.project_state import ProjectState, ProjectStatus
from src.domain.interfaces.project_repository import ProjectRepository

class SQLiteProjectRepository(ProjectRepository):
    """aiosqlite-backed repository for ProjectState aggregates."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def _row_to_entity(self, row: Dict[str, Any]) -> ProjectState:
        archived_at = datetime.fromisoformat(row["archived_at"]) if row.get("archived_at") else None
        return ProjectState(
            guild_id=row["guild_id"],
            status=ProjectStatus(row["status"]),
            archived_at=archived_at,
            archived_by=row.get("archived_by")
        )

    async def get_state(self, guild_id: str) -> Optional[ProjectState]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM project_state WHERE guild_id = ?",
                (guild_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return self._row_to_entity(dict(row)) if row else None

    async def save_state(self, state: ProjectState) -> None:
        archived_str = state.archived_at.isoformat() if state.archived_at else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO project_state (guild_id, status, archived_at, archived_by)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(guild_id) DO UPDATE SET
                    status = excluded.status,
                    archived_at = excluded.archived_at,
                    archived_by = excluded.archived_by
            """, (state.guild_id, state.status.value, archived_str, state.archived_by))
            await db.commit()
