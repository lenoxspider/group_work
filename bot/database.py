import aiosqlite
import logging
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from bot.config import DATABASE_PATH

logger = logging.getLogger("bot.database")

class Database:
    def __init__(self, db_path: str = DATABASE_PATH):
        self.db_path = db_path

    async def initialize(self):
        """Initializes database tables and creates migrations if needed."""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            
            # Tasks table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    guild_id TEXT,
                    channel_id TEXT,
                    message_id TEXT,
                    description TEXT NOT NULL,
                    assigned_to TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    completed_at TEXT NULL,
                    reminded_24h INTEGER DEFAULT 0,
                    reminded_1h INTEGER DEFAULT 0
                )
            """)

            # Deadlines table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS deadlines (
                    deadline_id TEXT PRIMARY KEY,
                    guild_id TEXT,
                    channel_id TEXT,
                    message_id TEXT,
                    name TEXT NOT NULL,
                    due_datetime TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    is_completed INTEGER DEFAULT 0,
                    reminded_72h INTEGER DEFAULT 0,
                    reminded_24h INTEGER DEFAULT 0,
                    reminded_6h INTEGER DEFAULT 0
                )
            """)

            # Member activity table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS member_activity (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    files_submitted INTEGER DEFAULT 0,
                    tasks_completed INTEGER DEFAULT 0,
                    last_active TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            # File submissions vault table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS submissions (
                    submission_id TEXT PRIMARY KEY,
                    guild_id TEXT,
                    user_id TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    submitted_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

            await db.commit()
            logger.info("Database initialized successfully.")

    # ------------------ Tasks CRUD ------------------
    async def create_task(self, task_id: str, guild_id: str, channel_id: Optional[str],
                          message_id: Optional[str], description: str, assigned_to: str,
                          due_date: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO tasks (task_id, guild_id, channel_id, message_id, description, assigned_to, due_date)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (task_id, str(guild_id), str(channel_id) if channel_id else None,
                  str(message_id) if message_id else None, description, str(assigned_to), due_date))
            await db.commit()

    async def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def get_pending_tasks(self, guild_id: Optional[str] = None) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM tasks WHERE completed_at IS NULL"
            params: List[Any] = []
            if guild_id:
                query += " AND guild_id = ?"
                params.append(str(guild_id))
            query += " ORDER BY due_date ASC"
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def complete_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM tasks WHERE task_id = ?", (task_id,)) as cursor:
                task = await cursor.fetchone()
                if not task:
                    return None
                task_dict = dict(task)

            await db.execute("""
                UPDATE tasks
                SET completed_at = ?
                WHERE task_id = ?
            """, (now_str, task_id))

            # Increment tasks_completed in member_activity
            await db.execute("""
                INSERT INTO member_activity (guild_id, user_id, tasks_completed, last_active)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    tasks_completed = tasks_completed + 1,
                    last_active = excluded.last_active
            """, (task_dict["guild_id"], task_dict["assigned_to"], now_str))

            await db.commit()
            task_dict["completed_at"] = now_str
            return task_dict

    async def mark_task_reminded(self, task_id: str, reminder_type: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            col = "reminded_24h" if reminder_type == "24h" else "reminded_1h"
            await db.execute(f"UPDATE tasks SET {col} = 1 WHERE task_id = ?", (task_id,))
            await db.commit()

    # ------------------ Deadlines CRUD ------------------
    async def create_deadline(self, deadline_id: str, guild_id: str, channel_id: str,
                              message_id: str, name: str, due_datetime: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO deadlines (deadline_id, guild_id, channel_id, message_id, name, due_datetime)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (deadline_id, str(guild_id), str(channel_id), str(message_id), name, due_datetime))
            await db.commit()

    async def get_active_deadlines(self, guild_id: Optional[str] = None) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM deadlines WHERE is_completed = 0"
            params: List[Any] = []
            if guild_id:
                query += " AND guild_id = ?"
                params.append(str(guild_id))
            query += " ORDER BY due_datetime ASC"
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

    async def get_deadline(self, deadline_id: str) -> Optional[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM deadlines WHERE deadline_id = ?", (deadline_id,)) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def mark_deadline_completed(self, deadline_id: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("UPDATE deadlines SET is_completed = 1 WHERE deadline_id = ?", (deadline_id,))
            await db.commit()

    async def mark_deadline_reminded(self, deadline_id: str, reminder_tier: str) -> None:
        async with aiosqlite.connect(self.db_path) as db:
            col = f"reminded_{reminder_tier}"
            await db.execute(f"UPDATE deadlines SET {col} = 1 WHERE deadline_id = ?", (deadline_id,))
            await db.commit()

    # ------------------ Member Activity & Report ------------------
    async def increment_message_count(self, guild_id: str, user_id: str) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO member_activity (guild_id, user_id, message_count, last_active)
                VALUES (?, ?, 1, ?)
                ON CONFLICT(guild_id, user_id) DO UPDATE SET
                    message_count = message_count + 1,
                    last_active = excluded.last_active
            """, (str(guild_id), str(user_id), now_str))
            await db.commit()

    async def log_file_submission(self, submission_id: str, user_id: str,
                                  original_filename: str, stored_filename: str,
                                  file_hash: str, file_size: int, guild_id: Optional[str] = None) -> None:
        now_str = datetime.now(timezone.utc).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("""
                INSERT INTO submissions (submission_id, guild_id, user_id, original_filename, stored_filename, file_hash, file_size, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (submission_id, str(guild_id) if guild_id else None, str(user_id),
                  original_filename, stored_filename, file_hash, file_size, now_str))

            # Update member activity across the guild or specific guild
            if guild_id:
                await db.execute("""
                    INSERT INTO member_activity (guild_id, user_id, files_submitted, last_active)
                    VALUES (?, ?, 1, ?)
                    ON CONFLICT(guild_id, user_id) DO UPDATE SET
                        files_submitted = files_submitted + 1,
                        last_active = excluded.last_active
                """, (str(guild_id), str(user_id), now_str))
            else:
                # If DM submitted without guild context, update all guild records for this user
                await db.execute("""
                    UPDATE member_activity
                    SET files_submitted = files_submitted + 1,
                        last_active = ?
                    WHERE user_id = ?
                """, (now_str, str(user_id)))
            await db.commit()

    async def get_member_stats(self, guild_id: str, user_id: str) -> Dict[str, Any]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT message_count, files_submitted, tasks_completed, last_active
                FROM member_activity
                WHERE guild_id = ? AND user_id = ?
            """, (str(guild_id), str(user_id))) as cursor:
                row = await cursor.fetchone()
                if row:
                    data = dict(row)
                else:
                    data = {
                        "message_count": 0,
                        "files_submitted": 0,
                        "tasks_completed": 0,
                        "last_active": None
                    }

            # Also fetch open and completed task counts from tasks table
            async with db.execute("""
                SELECT 
                    COUNT(CASE WHEN completed_at IS NOT NULL THEN 1 END) as completed_tasks,
                    COUNT(CASE WHEN completed_at IS NULL THEN 1 END) as pending_tasks
                FROM tasks
                WHERE guild_id = ? AND assigned_to = ?
            """, (str(guild_id), str(user_id))) as cursor:
                t_row = await cursor.fetchone()
                if t_row:
                    data["tasks_completed"] = max(data["tasks_completed"], t_row["completed_tasks"])
                    data["pending_tasks"] = t_row["pending_tasks"]
                else:
                    data["pending_tasks"] = 0

            return data

    async def get_guild_activity_report(self, guild_id: str) -> List[Dict[str, Any]]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("""
                SELECT user_id, message_count, files_submitted, tasks_completed, last_active
                FROM member_activity
                WHERE guild_id = ?
                ORDER BY (tasks_completed * 3 + files_submitted * 2 + message_count * 0.1) DESC
            """, (str(guild_id),)) as cursor:
                rows = await cursor.fetchall()
                return [dict(r) for r in rows]

# Global DB instance
db_instance = Database()
