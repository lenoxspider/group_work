"""SQLite persistence for the community member registry and tribunal cases."""

from typing import List, Optional

from src.infrastructure.database.sqlite import connect

from src.plugins.community.domain import (
    CASE_CONVICTED,
    CASE_OPEN,
    CATIZEN,
    CITIZEN,
    Case,
    Member,
)

_CASE_COLS = (
    "case_id, guild_id, accuser_id, accused_id, law_id, evidence, defense, status, "
    "guilty_votes, innocent_votes, round, message_id, channel_id, sentenced, "
    "created_at, opened_at, resolved_at"
)


class SQLiteCommunityRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # --- Members ---

    async def register(self, member: Member) -> None:
        query = """
            INSERT OR IGNORE INTO member_registry (
                guild_id, user_id, status, intro_task_id, intro_done, joined_at, signed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """
        async with connect(self.db_path) as db:
            await db.execute(
                query,
                (
                    member.guild_id, member.user_id, member.status, member.intro_task_id,
                    1 if member.intro_done else 0, member.joined_at, member.signed_at,
                ),
            )
            await db.commit()

    async def get_member(self, guild_id: str, user_id: str) -> Optional[Member]:
        query = """
            SELECT guild_id, user_id, status, intro_task_id, intro_done, joined_at, signed_at
            FROM member_registry WHERE guild_id = ? AND user_id = ?
        """
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, user_id)) as cur:
                row = await cur.fetchone()
                return self._row_to_member(row) if row else None

    async def list_citizens(self, guild_id: str) -> List[str]:
        query = "SELECT user_id FROM member_registry WHERE guild_id = ? AND status = ?"
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, CITIZEN)) as cur:
                rows = await cur.fetchall()
                return [r[0] for r in rows]

    async def list_pending_signers(self, guild_id: str, nudge_before: str) -> List[Member]:
        """Catizens who did the work (intro complete) but never signed.

        `nudge_before` is an ISO cutoff: only rows never nudged, or nudged
        before that moment, come back.
        """
        query = """
            SELECT guild_id, user_id, status, intro_task_id, intro_done, joined_at, signed_at
            FROM member_registry
            WHERE guild_id = ? AND status = ? AND intro_done = 1 AND signed_at IS NULL
              AND (sign_nudge_at IS NULL OR sign_nudge_at < ?)
        """
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, CATIZEN, nudge_before)) as cur:
                rows = await cur.fetchall()
                return [self._row_to_member(r) for r in rows]

    async def set_sign_nudge(self, guild_id: str, user_id: str, ts: str) -> None:
        query = "UPDATE member_registry SET sign_nudge_at = ? WHERE guild_id = ? AND user_id = ?"
        async with connect(self.db_path) as db:
            await db.execute(query, (ts, guild_id, user_id))
            await db.commit()

    async def set_mark(self, guild_id: str, user_id: str, mark: str) -> None:
        query = "UPDATE member_registry SET mark = ? WHERE guild_id = ? AND user_id = ?"
        async with connect(self.db_path) as db:
            await db.execute(query, (mark, guild_id, user_id))
            await db.commit()

    async def get_mark(self, guild_id: str, user_id: str) -> Optional[str]:
        query = "SELECT mark FROM member_registry WHERE guild_id = ? AND user_id = ?"
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, user_id)) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def count_trials(self, guild_id: str, user_id: str) -> int:
        """How many tribunal cases this member has stood accused in."""
        query = "SELECT COUNT(*) FROM court_cases WHERE guild_id = ? AND accused_id = ?"
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, user_id)) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    async def list_unstarted_catizens(
        self, guild_id: str, joined_before: str, nudge_before: str
    ) -> List[Member]:
        """Catizens who joined a while ago and never even started their intro.

        The intro task is exempt from the Wall of Shame, so without this nobody
        ever notices a member who joins and then does nothing at all.
        """
        query = """
            SELECT guild_id, user_id, status, intro_task_id, intro_done, joined_at, signed_at
            FROM member_registry
            WHERE guild_id = ? AND status = ? AND intro_done = 0 AND signed_at IS NULL
              AND joined_at < ?
              AND (sign_nudge_at IS NULL OR sign_nudge_at < ?)
        """
        async with connect(self.db_path) as db:
            async with db.execute(
                query, (guild_id, CATIZEN, joined_before, nudge_before)
            ) as cur:
                rows = await cur.fetchall()
                return [self._row_to_member(r) for r in rows]

    async def sign(self, guild_id: str, user_id: str, signed_at: str) -> None:
        query = "UPDATE member_registry SET status = ?, signed_at = ? WHERE guild_id = ? AND user_id = ?"
        async with connect(self.db_path) as db:
            await db.execute(query, (CITIZEN, signed_at, guild_id, user_id))
            await db.commit()

    async def set_intro_task(self, guild_id: str, user_id: str, task_id: str) -> None:
        query = "UPDATE member_registry SET intro_task_id = ? WHERE guild_id = ? AND user_id = ?"
        async with connect(self.db_path) as db:
            await db.execute(query, (task_id, guild_id, user_id))
            await db.commit()

    async def mark_intro_done(self, guild_id: str, user_id: str) -> None:
        query = "UPDATE member_registry SET intro_done = 1 WHERE guild_id = ? AND user_id = ?"
        async with connect(self.db_path) as db:
            await db.execute(query, (guild_id, user_id))
            await db.commit()

    @staticmethod
    def _row_to_member(row) -> Member:
        return Member(
            guild_id=row[0], user_id=row[1],
            status=row[2] if row[2] in (CATIZEN, CITIZEN) else CATIZEN,
            intro_task_id=row[3], intro_done=bool(row[4]), joined_at=row[5], signed_at=row[6],
        )

    # --- Cases ---

    async def save_case(self, case: Case) -> None:
        query = f"""
            INSERT INTO court_cases ({_CASE_COLS})
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                evidence = excluded.evidence,
                defense = excluded.defense,
                status = excluded.status,
                guilty_votes = excluded.guilty_votes,
                innocent_votes = excluded.innocent_votes,
                round = excluded.round,
                message_id = excluded.message_id,
                channel_id = excluded.channel_id,
                sentenced = excluded.sentenced,
                opened_at = excluded.opened_at,
                resolved_at = excluded.resolved_at
        """
        async with connect(self.db_path) as db:
            await db.execute(
                query,
                (
                    case.case_id, case.guild_id, case.accuser_id, case.accused_id, case.law_id,
                    case.evidence, case.defense, case.status, case.guilty_votes, case.innocent_votes,
                    case.round, case.message_id, case.channel_id, 1 if case.sentenced else 0,
                    case.created_at, case.opened_at, case.resolved_at,
                ),
            )
            await db.commit()

    async def get_case(self, case_id: str) -> Optional[Case]:
        query = f"SELECT {_CASE_COLS} FROM court_cases WHERE case_id = ?"
        async with connect(self.db_path) as db:
            async with db.execute(query, (case_id,)) as cur:
                row = await cur.fetchone()
                return self._row_to_case(row) if row else None

    async def get_case_by_message(self, message_id: str) -> Optional[Case]:
        query = f"SELECT {_CASE_COLS} FROM court_cases WHERE message_id = ?"
        async with connect(self.db_path) as db:
            async with db.execute(query, (message_id,)) as cur:
                row = await cur.fetchone()
                return self._row_to_case(row) if row else None

    async def list_open_cases(self, guild_id: str) -> List[Case]:
        query = f"SELECT {_CASE_COLS} FROM court_cases WHERE guild_id = ? AND status = ?"
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, CASE_OPEN)) as cur:
                rows = await cur.fetchall()
                return [self._row_to_case(r) for r in rows]

    async def list_convicted_unsentenced(self, guild_id: str) -> List[Case]:
        query = (
            f"SELECT {_CASE_COLS} FROM court_cases "
            "WHERE guild_id = ? AND status = ? AND round = 1 AND sentenced = 0"
        )
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, CASE_CONVICTED)) as cur:
                rows = await cur.fetchall()
                return [self._row_to_case(r) for r in rows]

    async def has_open_case_for(self, guild_id: str, accused_id: str) -> bool:
        query = "SELECT 1 FROM court_cases WHERE guild_id = ? AND accused_id = ? AND status = ? LIMIT 1"
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, accused_id, CASE_OPEN)) as cur:
                return await cur.fetchone() is not None

    async def count_prior_convictions(self, guild_id: str, accused_id: str, law_id: str, exclude_case_id: str) -> int:
        query = (
            "SELECT COUNT(*) FROM court_cases WHERE guild_id = ? AND accused_id = ? "
            "AND law_id = ? AND status = ? AND sentenced = 1 AND case_id != ?"
        )
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, accused_id, law_id, CASE_CONVICTED, exclude_case_id)) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    @staticmethod
    def _row_to_case(row) -> Case:
        return Case(
            case_id=row[0], guild_id=row[1], accuser_id=row[2], accused_id=row[3], law_id=row[4],
            evidence=row[5], defense=row[6], status=row[7], guilty_votes=row[8], innocent_votes=row[9],
            round=row[10], message_id=row[11] or "", channel_id=row[12] or "",
            sentenced=bool(row[13]), created_at=row[14], opened_at=row[15], resolved_at=row[16],
        )
