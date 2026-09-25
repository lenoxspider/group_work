"""Integration tests for ChannelBindingRepository and AlertFireRepository."""

import os
import tempfile
import unittest
from datetime import datetime, timezone

from src.infrastructure.database.connection import DatabaseManager
from src.domain.entities.channel_binding import ChannelBinding
from src.domain.entities.alert_fire import AlertFire
from src.infrastructure.database.channel_binding_sqlite_repo import SQLiteChannelBindingRepository
from src.infrastructure.database.alert_fire_sqlite_repo import SQLiteAlertFireRepository

class TestChannelAndAlertRepositories(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.db_path = self.temp_db.name
        self.temp_db.close()

        self.db_manager = DatabaseManager(self.db_path)
        await self.db_manager.initialize_schema()
        self.binding_repo = SQLiteChannelBindingRepository(self.db_path)
        self.alert_repo = SQLiteAlertFireRepository(self.db_path)

    async def asyncTearDown(self):
        if os.path.exists(self.db_path):
            try:
                os.remove(self.db_path)
            except OSError:
                pass

    async def test_channel_binding_lifecycle(self):
        now = datetime.now(timezone.utc)
        binding = ChannelBinding(
            guild_id="111",
            channel_key="tasks",
            channel_id="999888777",
            updated_at=now
        )
        await self.binding_repo.save_binding(binding)

        ch_id = await self.binding_repo.get_binding("111", "tasks")
        self.assertEqual(ch_id, "999888777")

        all_bindings = await self.binding_repo.list_bindings("111")
        self.assertEqual(all_bindings, {"tasks": "999888777"})

        # Update binding
        updated_binding = ChannelBinding(
            guild_id="111",
            channel_key="tasks",
            channel_id="111222333",
            updated_at=now
        )
        await self.binding_repo.save_binding(updated_binding)
        self.assertEqual(await self.binding_repo.get_binding("111", "tasks"), "111222333")

        # Delete binding
        await self.binding_repo.delete_binding("111", "tasks")
        self.assertIsNone(await self.binding_repo.get_binding("111", "tasks"))

    async def test_alert_fire_idempotency(self):
        now = datetime.now(timezone.utc)
        record1 = AlertFire(task_id=42, alert_tier="T-6h", fired_at=now)

        # First fire succeeds
        first = await self.alert_repo.record_fire(record1)
        self.assertTrue(first)

        # Second fire for same task and tier returns False (preventing duplicates!)
        second = await self.alert_repo.record_fire(record1)
        self.assertFalse(second)

        self.assertTrue(await self.alert_repo.has_fired(42, "T-6h"))
        self.assertFalse(await self.alert_repo.has_fired(42, "T-1h"))

        # Fire different tier for same task
        record2 = AlertFire(task_id=42, alert_tier="T-1h", fired_at=now)
        self.assertTrue(await self.alert_repo.record_fire(record2))

        tiers = await self.alert_repo.list_fired_tiers(42)
        self.assertIn("T-6h", tiers)
        self.assertIn("T-1h", tiers)
        self.assertEqual(len(tiers), 2)

if __name__ == "__main__":
    unittest.main()
