"""
SQLite database connection and migration manager.

What it does:
- Initializes SQLite tables and ensures schema consistency.
- Manages connection context for aiosqlite.

What it does NOT do:
- Does NOT execute domain business logic.
- Does NOT interact with Discord APIs.
"""

import aiosqlite
import logging

logger = logging.getLogger("infrastructure.database")

class DatabaseManager:
    """Manages SQLite schema creation and connection pooling."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def initialize_schema(self) -> None:
        """Initializes all required tables and indexes."""
        async with aiosqlite.connect(self.db_path) as db:
            # 1. Tasks table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT,
                    message_id TEXT,
                    description TEXT NOT NULL,
                    assigned_to TEXT NOT NULL,
                    due_date TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    completed_at TEXT NULL,
                    reminded_24h INTEGER DEFAULT 0,
                    reminded_1h INTEGER DEFAULT 0,
                    is_in_progress INTEGER DEFAULT 0,
                    shame_logged INTEGER DEFAULT 0
                )
            """)

            # 2. Deadlines table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS deadlines (
                    deadline_id TEXT PRIMARY KEY,
                    guild_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    message_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    due_datetime TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    is_completed INTEGER DEFAULT 0,
                    reminded_72h INTEGER DEFAULT 0,
                    reminded_24h INTEGER DEFAULT 0,
                    reminded_6h INTEGER DEFAULT 0
                )
            """)

            # 3. Member activity table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS member_activity (
                    guild_id TEXT NOT NULL,
                    user_id TEXT NOT NULL,
                    message_count INTEGER DEFAULT 0,
                    files_submitted INTEGER DEFAULT 0,
                    tasks_completed INTEGER DEFAULT 0,
                    on_time_tasks INTEGER DEFAULT 0,
                    current_streak INTEGER DEFAULT 0,
                    best_streak INTEGER DEFAULT 0,
                    last_active TEXT NOT NULL,
                    PRIMARY KEY (guild_id, user_id)
                )
            """)

            # 4. Vault submissions table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS vault_submissions (
                    submission_id TEXT PRIMARY KEY,
                    guild_id TEXT,
                    user_id TEXT NOT NULL,
                    original_filename TEXT NOT NULL,
                    stored_filename TEXT NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_size INTEGER DEFAULT 0,
                    submitted_at TEXT NOT NULL
                )
            """)

            # 5. Project state table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS project_state (
                    guild_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    archived_at TEXT,
                    archived_by TEXT
                )
            """)

            # Migrations for existing databases
            migrations = [
                ("tasks", "is_in_progress", "INTEGER DEFAULT 0"),
                ("tasks", "shame_logged", "INTEGER DEFAULT 0"),
                ("member_activity", "on_time_tasks", "INTEGER DEFAULT 0"),
                ("member_activity", "current_streak", "INTEGER DEFAULT 0"),
                ("member_activity", "best_streak", "INTEGER DEFAULT 0"),
            ]
            for table, col, col_type in migrations:
                try:
                    await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                except Exception:
                    pass

            await db.commit()
            logger.info("SQLite schema initialized successfully at %s", self.db_path)
