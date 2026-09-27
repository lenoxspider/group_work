"""SQLite persistence for the community member registry."""

from typing import Optional

import aiosqlite

from src.plugins.community.domain import CATIZEN, CITIZEN, Member


class SQLiteCommunityRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    async def register(self, member: Member) -> None:
        """Insert a member row, ignoring if they already exist (rejoin safety)."""
        query = """
            INSERT OR IGNORE INTO member_registry (
                guild_id, user_id, status, intro_task_id, intro_done, joined_at, signed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                query,
                (
                    member.guild_id,
                    member.user_id,
                    member.status,
                    member.intro_task_id,
                    1 if member.intro_done else 0,
                    member.joined_at,
                    member.signed_at,
                ),
            )
            await db.commit()

    async def get_member(self, guild_id: str, user_id: str) -> Optional[Member]:
        query = """
            SELECT guild_id, user_id, status, intro_task_id, intro_done, joined_at, signed_at
            FROM member_registry WHERE guild_id = ? AND user_id = ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, (guild_id, user_id)) as cur:
                row = await cur.fetchone()
                return self._row_to_member(row) if row else None

    async def sign(self, guild_id: str, user_id: str, signed_at: str) -> None:
        query = """
            UPDATE member_registry SET status = ?, signed_at = ?
            WHERE guild_id = ? AND user_id = ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, (CITIZEN, signed_at, guild_id, user_id))
            await db.commit()

    async def set_intro_task(self, guild_id: str, user_id: str, task_id: str) -> None:
        query = """
            UPDATE member_registry SET intro_task_id = ?
            WHERE guild_id = ? AND user_id = ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, (task_id, guild_id, user_id))
            await db.commit()

    async def mark_intro_done(self, guild_id: str, user_id: str) -> None:
        query = """
            UPDATE member_registry SET intro_done = 1
            WHERE guild_id = ? AND user_id = ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, (guild_id, user_id))
            await db.commit()

    @staticmethod
    def _row_to_member(row) -> Member:
        return Member(
            guild_id=row[0],
            user_id=row[1],
            status=row[2] if row[2] in (CATIZEN, CITIZEN) else CATIZEN,
            intro_task_id=row[3],
            intro_done=bool(row[4]),
            joined_at=row[5],
            signed_at=row[6],
        )