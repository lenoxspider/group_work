"""Integration tests for the community registry's nudge queries.

Two failure modes these guard, both of which happened in production:

1. A member completed their introduction but never signed, and the only prompt
   was an ephemeral line that vanished - they sat as a catizen for two days.
2. A member joined and never did anything at all. The intro task is exempt from
   the Wall of Shame, so nothing in the system ever noticed them.

Schema is built through DatabaseManager so the sign_nudge_at migration is
exercised rather than assumed.
"""

import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

from src.infrastructure.database.connection import DatabaseManager
from src.plugins.community.domain import CATIZEN, CITIZEN, Member
from src.plugins.community.repository import SQLiteCommunityRepository
from src.plugins.community.schema import COMMUNITY_MIGRATIONS, COMMUNITY_SCHEMA

GUILD = "guild-registry"


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


class TestCommunityNudgeQueries(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        manager = DatabaseManager(self.db_path)
        manager.register_plugin_schema("community", COMMUNITY_SCHEMA)
        manager.register_plugin_migrations("community", COMMUNITY_MIGRATIONS)
        await manager.initialize_schema()
        self.repo = SQLiteCommunityRepository(self.db_path)
        self.now = datetime.now(timezone.utc)
        self.old = self.now - timedelta(days=7)
        self.recent = self.now - timedelta(hours=6)
        self.day_ago = self.now - timedelta(hours=24)

    async def asyncTearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    async def _add(self, user_id, status, intro_done, joined_at, signed_at=None):
        await self.repo.register(
            Member(
                guild_id=GUILD, user_id=user_id, status=status,
                intro_task_id=None, intro_done=intro_done,
                joined_at=_iso(joined_at), signed_at=signed_at,
            )
        )

    def _cutoffs(self):
        return (
            _iso(self.now - timedelta(days=2)),    # joined before
            _iso(self.now - timedelta(hours=24)),  # nudged before
        )

    async def test_migration_added_the_nudge_column(self):
        from src.infrastructure.database.sqlite import connect

        async with connect(self.db_path) as db:
            cols = [r[1] for r in await db.execute_fetchall("PRAGMA table_info(member_registry)")]
        self.assertIn("sign_nudge_at", cols)

    # --- list_pending_signers: did the work, never signed ---

    async def test_pending_signer_is_the_one_who_finished_the_intro(self):
        await self._add("stranded", CATIZEN, True, self.old)
        await self._add("notdone", CATIZEN, False, self.old)
        await self._add("signed", CITIZEN, True, self.old, signed_at=_iso(self.old))

        got = sorted(m.user_id for m in await self.repo.list_pending_signers(GUILD, self.day_ago.isoformat()))
        self.assertEqual(got, ["stranded"])

    async def test_pending_signer_drops_out_once_nudged(self):
        await self._add("stranded", CATIZEN, True, self.old)
        before = _iso(self.now - timedelta(hours=24))
        self.assertEqual(len(await self.repo.list_pending_signers(GUILD, before)), 1)

        await self.repo.set_sign_nudge(GUILD, "stranded", _iso(self.now))
        self.assertEqual(await self.repo.list_pending_signers(GUILD, before), [])

    async def test_pending_signer_returns_after_the_cooldown(self):
        await self._add("stranded", CATIZEN, True, self.old)
        await self.repo.set_sign_nudge(GUILD, "stranded", _iso(self.now - timedelta(hours=30)))
        before = _iso(self.now - timedelta(hours=24))
        got = await self.repo.list_pending_signers(GUILD, before)
        self.assertEqual([m.user_id for m in got], ["stranded"])

    async def test_signing_removes_them_from_the_pending_list(self):
        await self._add("stranded", CATIZEN, True, self.old)
        await self.repo.sign(GUILD, "stranded", _iso(self.now))
        self.assertEqual(await self.repo.list_pending_signers(GUILD, self.day_ago.isoformat()), [])

    # --- list_unstarted_catizens: joined and did nothing ---

    async def test_unstarted_excludes_everyone_with_a_reason_to_be_left_alone(self):
        joined_before, nudged_before = self._cutoffs()
        await self._add("ghost", CATIZEN, False, self.old)          # -> chase
        await self._add("fresh", CATIZEN, False, self.recent)        # joined 6h ago
        await self._add("didintro", CATIZEN, True, self.old)         # other nudge's job
        await self._add("signed", CITIZEN, True, self.old, signed_at=_iso(self.old))
        await self._add("nudged", CATIZEN, False, self.old)
        await self.repo.set_sign_nudge(GUILD, "nudged", _iso(self.now))

        got = sorted(
            m.user_id
            for m in await self.repo.list_unstarted_catizens(GUILD, joined_before, nudged_before)
        )
        self.assertEqual(got, ["ghost"])

    async def test_unstarted_respects_the_joined_cutoff(self):
        joined_before, nudged_before = self._cutoffs()
        await self._add("recent", CATIZEN, False, self.now - timedelta(days=1))
        self.assertEqual(
            await self.repo.list_unstarted_catizens(GUILD, joined_before, nudged_before), []
        )

    async def test_unstarted_drops_out_once_nudged(self):
        joined_before, nudged_before = self._cutoffs()
        await self._add("ghost", CATIZEN, False, self.old)
        await self.repo.set_sign_nudge(GUILD, "ghost", _iso(self.now))
        self.assertEqual(
            await self.repo.list_unstarted_catizens(GUILD, joined_before, nudged_before), []
        )

    async def test_the_two_nudges_never_claim_the_same_member(self):
        """One shared cooldown column, so a member cannot be DM'd twice a day."""
        joined_before, nudged_before = self._cutoffs()
        await self._add("didintro", CATIZEN, True, self.old)
        await self._add("ghost", CATIZEN, False, self.old)

        await self.repo.set_sign_nudge(GUILD, "didintro", _iso(self.now))
        await self.repo.set_sign_nudge(GUILD, "ghost", _iso(self.now))

        self.assertEqual(await self.repo.list_pending_signers(GUILD, nudged_before), [])
        self.assertEqual(
            await self.repo.list_unstarted_catizens(GUILD, joined_before, nudged_before), []
        )

    # --- citizens ---

    async def test_list_citizens_returns_only_signed_members(self):
        await self._add("alice", CITIZEN, True, self.old, signed_at=_iso(self.old))
        await self._add("bob", CITIZEN, False, self.old, signed_at=_iso(self.old))
        await self._add("cat", CATIZEN, True, self.old)

        self.assertEqual(sorted(await self.repo.list_citizens(GUILD)), ["alice", "bob"])

    async def test_queries_are_scoped_to_the_guild(self):
        await self._add("here", CATIZEN, True, self.old)
        await self.repo.register(
            Member(guild_id="other-guild", user_id="there", status=CATIZEN,
                   intro_done=True, joined_at=_iso(self.old))
        )
        got = [m.user_id for m in await self.repo.list_pending_signers(GUILD, self.day_ago.isoformat())]
        self.assertEqual(got, ["here"])


if __name__ == "__main__":
    unittest.main()
