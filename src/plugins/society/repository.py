"""SQLite repository for laws and proposals."""

from typing import List, Optional

import aiosqlite

from src.plugins.society.domain import Law, Proposal, utcnow


class SocietyRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # --- Laws ---

    async def save_law(self, law: Law) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO laws (law_id, guild_id, title, description, fine_amount, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (law.law_id, law.guild_id, law.title, law.description, law.fine_amount, law.created_at),
            )
            await db.commit()

    async def get_law(self, law_id: str) -> Optional[Law]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT law_id, guild_id, title, description, fine_amount, created_at FROM laws WHERE law_id = ?",
                (law_id,),
            ) as cur:
                row = await cur.fetchone()
                return Law(*row) if row else None

    async def list_laws(self, guild_id: str) -> List[Law]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT law_id, guild_id, title, description, fine_amount, created_at FROM laws WHERE guild_id = ? ORDER BY created_at",
                (guild_id,),
            ) as cur:
                rows = await cur.fetchall()
                return [Law(*r) for r in rows]

    async def delete_law(self, law_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM laws WHERE law_id = ?", (law_id,))
            await db.commit()

    # --- Proposals ---

    async def save_proposal(self, proposal: Proposal) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO proposals "
                "(proposal_id, guild_id, author_id, title, description, amount, status, approvals, rejections, created_at, resolved_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    proposal.proposal_id, proposal.guild_id, proposal.author_id, proposal.title,
                    proposal.description, proposal.amount, proposal.status, proposal.approvals,
                    proposal.rejections, proposal.created_at, proposal.resolved_at,
                ),
            )
            await db.commit()

    async def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT proposal_id, guild_id, author_id, title, description, amount, status, approvals, rejections, created_at, resolved_at "
                "FROM proposals WHERE proposal_id = ?",
                (proposal_id,),
            ) as cur:
                row = await cur.fetchone()
                return Proposal(*row) if row else None

    async def list_proposals(self, guild_id: str, status: Optional[str] = None) -> List[Proposal]:
        query = "SELECT proposal_id, guild_id, author_id, title, description, amount, status, approvals, rejections, created_at, resolved_at FROM proposals WHERE guild_id = ?"
        params = [guild_id]
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY created_at"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cur:
                rows = await cur.fetchall()
                return [Proposal(*r) for r in rows]

    async def update_proposal(self, proposal: Proposal) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE proposals SET status = ?, approvals = ?, rejections = ?, resolved_at = ? WHERE proposal_id = ?",
                (proposal.status, proposal.approvals, proposal.rejections, proposal.resolved_at, proposal.proposal_id),
            )
            await db.commit()