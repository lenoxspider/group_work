import os
import asyncio
import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from bot.database import Database
from bot.utils.helpers import (
    parse_datetime_input,
    generate_short_id,
    compute_file_hash,
    calculate_time_remaining,
    format_countdown_string
)

class TestBotCore(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_db = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
        self.temp_db.close()
        self.db = Database(self.temp_db.name)
        await self.db.initialize()

    async def asyncTearDown(self):
        if os.path.exists(self.temp_db.name):
            os.remove(self.temp_db.name)

    def test_helpers(self):
        # 1. Date parser
        dt = parse_datetime_input("2026-10-15")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.year, 2026)
        self.assertEqual(dt.month, 10)
        self.assertEqual(dt.day, 15)

        dt_time = parse_datetime_input("2026-10-15 14:30")
        self.assertIsNotNone(dt_time)
        self.assertEqual(dt_time.hour, 14)
        self.assertEqual(dt_time.minute, 30)

        # 2. Short ID generator
        task_id = generate_short_id("TASK")
        self.assertTrue(task_id.startswith("TASK-"))

        # 3. Hash computation
        sample_bytes = b"Hello Discord Group Work"
        h = compute_file_hash(sample_bytes)
        self.assertEqual(len(h), 64)

        # 4. Countdown formatter
        future_dt = datetime.now(timezone.utc) + timedelta(days=2, hours=3, minutes=10)
        countdown_str = format_countdown_string(future_dt)
        self.assertIn("2d", countdown_str)

    async def test_task_lifecycle(self):
        task_id = "TASK-001"
        due_iso = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        
        # Create
        await self.db.create_task(
            task_id=task_id,
            guild_id="123456",
            channel_id="999",
            message_id="888",
            description="Write literature review",
            assigned_to="555",
            due_date=due_iso
        )

        task = await self.db.get_task(task_id)
        self.assertIsNotNone(task)
        self.assertEqual(task["description"], "Write literature review")
        self.assertIsNone(task["completed_at"])

        # Pending list
        pending = await self.db.get_pending_tasks("123456")
        self.assertEqual(len(pending), 1)

        # Reminder flag update
        await self.db.mark_task_reminded(task_id, "24h")
        updated = await self.db.get_task(task_id)
        self.assertEqual(updated["reminded_24h"], 1)

        # Complete
        completed = await self.db.complete_task(task_id)
        self.assertIsNotNone(completed["completed_at"])

        # Check pending is now empty
        pending_after = await self.db.get_pending_tasks("123456")
        self.assertEqual(len(pending_after), 0)

    async def test_deadline_lifecycle(self):
        dl_id = "DL-001"
        due_iso = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

        await self.db.create_deadline(
            deadline_id=dl_id,
            guild_id="123456",
            channel_id="777",
            message_id="666",
            name="Final Report Submission",
            due_datetime=due_iso
        )

        dl = await self.db.get_deadline(dl_id)
        self.assertIsNotNone(dl)
        self.assertEqual(dl["name"], "Final Report Submission")
        self.assertEqual(dl["is_completed"], 0)

        # Mark 72h reminded
        await self.db.mark_deadline_reminded(dl_id, "72h")
        dl_reminded = await self.db.get_deadline(dl_id)
        self.assertEqual(dl_reminded["reminded_72h"], 1)

        # Complete
        await self.db.mark_deadline_completed(dl_id)
        active = await self.db.get_active_deadlines("123456")
        self.assertEqual(len(active), 0)

    async def test_activity_and_contribution_report(self):
        guild_id = "123456"
        user_a = "111"
        user_b = "222"

        # User A sends 5 messages
        for _ in range(5):
            await self.db.increment_message_count(guild_id, user_a)

        # User B sends 2 messages
        for _ in range(2):
            await self.db.increment_message_count(guild_id, user_b)

        # User A submits a file
        await self.db.log_file_submission(
            submission_id="SUB-001",
            user_id=user_a,
            original_filename="draft.pdf",
            stored_filename="draft_20260925_abc.pdf",
            file_hash="abcdef123456",
            file_size=10240,
            guild_id=guild_id
        )

        # Stats check
        stats_a = await self.db.get_member_stats(guild_id, user_a)
        self.assertEqual(stats_a["message_count"], 5)
        self.assertEqual(stats_a["files_submitted"], 1)

        stats_b = await self.db.get_member_stats(guild_id, user_b)
        self.assertEqual(stats_b["message_count"], 2)
        self.assertEqual(stats_b["files_submitted"], 0)

        # Guild leaderboard
        leaderboard = await self.db.get_guild_activity_report(guild_id)
        self.assertEqual(len(leaderboard), 2)
        self.assertEqual(leaderboard[0]["user_id"], user_a)

if __name__ == "__main__":
    unittest.main()
