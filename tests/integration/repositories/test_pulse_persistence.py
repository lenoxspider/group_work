"""Integration tests for pulse persistence across a restart.

The failure these guard: PulseService.active was in-memory only, so a restart
mid-pulse orphaned it. The message sat in #pulse with no judge, a Snap Trial
under vote never rendered a verdict (no fine, no compensation, votes already
cast against it), and a fresh pulse could fire on top of the stale one.

Recovery works because the tally reads reaction state live from the Discord
message, so votes cast while the bot was down are not lost - only the pulse
record needs to survive.
"""

import json
import os
import tempfile
import unittest
from datetime import timedelta

from src.infrastructure.database.connection import DatabaseManager
from src.plugins.pulse.domain import ActivePulse, utcnow
from src.plugins.pulse.repository import SQLitePulseRepository
from src.plugins.pulse.schema import PULSE_SCHEMA
from src.plugins.pulse.service import PulseService

GUILD = "guild-persist"


class FakeMessage:
    def __init__(self, message_id=555000111):
        self.id = message_id

    async def add_reaction(self, emoji):
        pass


class FakeChannel:
    def __init__(self, channel_id=777000222):
        self.id = channel_id
        self.sent = []

    async def send(self, content=None, embed=None, allowed_mentions=None):
        self.sent.append(content)
        return FakeMessage()


class TestPulsePersistence(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        manager = DatabaseManager(self.db_path)
        manager.register_plugin_schema("pulse", PULSE_SCHEMA)
        await manager.initialize_schema()
        self.repo = SQLitePulseRepository(self.db_path)

    async def asyncTearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _pulse(self, **overrides) -> ActivePulse:
        fields = dict(
            guild_id=GUILD, channel_id="777000222", message_id="555000111",
            kind="snap_trial", label="Snap Trial", answer="", mode="vote",
            started_at=utcnow(),
            accept=("echo", "anecho"),
            vote_options={"✅": "guilty", "❌": "innocent"},
            timeout_seconds=300,
            data={"accused_id": "111", "crime": "hoarding bread"},
        )
        fields.update(overrides)
        return ActivePulse(**fields)

    # --- round trip ---

    async def test_every_field_survives_the_round_trip(self):
        original = self._pulse()
        await self.repo.save_active(original)
        restored = await self.repo.get_active(GUILD)

        self.assertIsNotNone(restored)
        self.assertEqual(restored.guild_id, original.guild_id)
        self.assertEqual(restored.channel_id, original.channel_id)
        self.assertEqual(restored.message_id, original.message_id)
        self.assertEqual(restored.kind, original.kind)
        self.assertEqual(restored.label, original.label)
        self.assertEqual(restored.mode, original.mode)
        self.assertEqual(restored.timeout_seconds, 300)
        self.assertEqual(restored.accept, ("echo", "anecho"))
        self.assertEqual(restored.vote_options, {"✅": "guilty", "❌": "innocent"})
        self.assertEqual(restored.data, {"accused_id": "111", "crime": "hoarding bread"})

    async def test_started_at_survives_so_expiry_still_works(self):
        """Without the original timestamp a restored pulse never expires."""
        original = self._pulse(started_at=utcnow() - timedelta(seconds=999))
        await self.repo.save_active(original)
        restored = await self.repo.get_active(GUILD)
        self.assertTrue(restored.is_expired())

    async def test_a_fresh_pulse_is_not_marked_expired(self):
        await self.repo.save_active(self._pulse())
        restored = await self.repo.get_active(GUILD)
        self.assertFalse(restored.is_expired())

    async def test_saving_twice_replaces_rather_than_duplicates(self):
        await self.repo.save_active(self._pulse(message_id="1"))
        await self.repo.save_active(self._pulse(message_id="2"))
        rows = await self.repo.list_active()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].message_id, "2")

    async def test_list_active_covers_every_guild(self):
        await self.repo.save_active(self._pulse(guild_id="g1"))
        await self.repo.save_active(self._pulse(guild_id="g2"))
        self.assertEqual({p.guild_id for p in await self.repo.list_active()}, {"g1", "g2"})

    async def test_clear_active_removes_only_that_guild(self):
        await self.repo.save_active(self._pulse(guild_id="g1"))
        await self.repo.save_active(self._pulse(guild_id="g2"))
        await self.repo.clear_active("g1")
        self.assertIsNone(await self.repo.get_active("g1"))
        self.assertIsNotNone(await self.repo.get_active("g2"))

    # --- corrupt rows ---

    async def test_a_corrupt_row_is_dropped_not_raised_over(self):
        """One unreadable pulse must not stop the plugin from booting."""
        from src.infrastructure.database.sqlite import connect

        async with connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO pulse_active (guild_id, channel_id, message_id, kind, label, "
                "answer, mode, started_at, accept, vote_options, timeout_seconds, data) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                ("bad", "c", "m", "k", "l", "", "vote", "not-a-timestamp",
                 "{invalid json", "{also bad", 300, "nope"),
            )
            await db.commit()

        await self.repo.save_active(self._pulse(guild_id="good"))
        restored = await self.repo.list_active()
        self.assertEqual([p.guild_id for p in restored], ["good"])

    # --- service level: a simulated restart ---

    async def test_fire_persists_the_live_pulse(self):
        service = PulseService(self.repo)
        await service.fire(GUILD, FakeChannel())
        self.assertIsNotNone(await self.repo.get_active(GUILD))

    async def test_a_restart_reloads_the_pulse_that_was_live(self):
        before = PulseService(self.repo)
        fired = await before.fire(GUILD, FakeChannel())
        self.assertIsNotNone(fired)

        after = PulseService(self.repo)          # fresh process, empty memory
        self.assertIsNone(after.active_pulse(GUILD))

        count = await after.restore()
        restored = after.active_pulse(GUILD)
        self.assertEqual(count, 1)
        self.assertIsNotNone(restored)
        self.assertEqual(restored.message_id, fired.message_id)
        self.assertEqual(restored.kind, fired.kind)
        self.assertEqual(restored.mode, fired.mode)

    async def test_restore_with_nothing_persisted_is_a_clean_noop(self):
        service = PulseService(self.repo)
        self.assertEqual(await service.restore(), 0)
        self.assertIsNone(service.active_pulse(GUILD))

    async def test_service_clear_removes_it_from_disk_too(self):
        """Otherwise the pulse would resurrect on the next restart."""
        service = PulseService(self.repo)
        await service.fire(GUILD, FakeChannel())
        await service.clear(GUILD)
        self.assertIsNone(service.active_pulse(GUILD))
        self.assertIsNone(await self.repo.get_active(GUILD))

    async def test_a_restored_pulse_cannot_be_double_fired_over(self):
        """The other half of the bug: fire() must see the restored pulse."""
        before = PulseService(self.repo)
        await before.fire(GUILD, FakeChannel())

        after = PulseService(self.repo)
        await after.restore()
        self.assertIsNone(await after.fire(GUILD, FakeChannel()))

    async def test_persisted_row_stores_json_not_python_repr(self):
        """Python repr uses single quotes, which json.loads would reject."""
        await self.repo.save_active(self._pulse())
        from src.infrastructure.database.sqlite import connect

        async with connect(self.db_path) as db:
            rows = await db.execute_fetchall(
                "SELECT accept, vote_options, data FROM pulse_active WHERE guild_id = ?",
                (GUILD,),
            )
        for cell in rows[0]:
            json.loads(cell)  # must not raise


if __name__ == "__main__":
    unittest.main()
