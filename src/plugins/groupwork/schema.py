"""Groupwork (accountability + squid game) plugin schema.

Extracted from connection.py so the plugin owns its tables and the
shared DatabaseManager stays schema-agnostic.
"""

GROUPWORK_SCHEMA = [
    """
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
        reminded_6h INTEGER DEFAULT 0,
        reminded_1h INTEGER DEFAULT 0,
        is_in_progress INTEGER DEFAULT 0,
        shame_logged INTEGER DEFAULT 0,
        verifier_id TEXT,
        verified_at TEXT,
        verified_by TEXT
    )
    """,
    """
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
    """,
    """
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
    """,
    """
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
    """,
    """
    CREATE TABLE IF NOT EXISTS project_state (
        guild_id TEXT PRIMARY KEY,
        status TEXT NOT NULL,
        archived_at TEXT,
        archived_by TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS extension_requests (
        request_id TEXT PRIMARY KEY,
        task_id TEXT NOT NULL,
        guild_id TEXT NOT NULL,
        requester_id TEXT NOT NULL,
        proposed_due_date TEXT NOT NULL,
        reason TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        approvals TEXT NOT NULL DEFAULT '',
        rejections TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        resolved_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS member_preferences (
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        timezone_name TEXT NOT NULL DEFAULT 'UTC',
        quiet_hours_start INTEGER DEFAULT 23,
        quiet_hours_end INTEGER DEFAULT 8,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS squid_players (
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        player_number TEXT NOT NULL,
        is_alive INTEGER DEFAULT 1,
        survival_streak INTEGER DEFAULT 0,
        elimination_reason TEXT,
        eliminated_at TEXT,
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS squid_seasons (
        guild_id TEXT PRIMARY KEY,
        pot_amount INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        current_game TEXT DEFAULT 'Red Light Green Light'
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS movement_anomalies (
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        reason TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS channel_bindings (
        guild_id TEXT NOT NULL,
        channel_key TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, channel_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS alert_fires (
        task_id INTEGER NOT NULL,
        alert_tier TEXT NOT NULL,
        fired_at TEXT NOT NULL,
        PRIMARY KEY (task_id, alert_tier)
    )
    """,
]

GROUPWORK_MIGRATIONS = [
    ("tasks", "reminded_6h", "INTEGER DEFAULT 0"),
    ("tasks", "is_in_progress", "INTEGER DEFAULT 0"),
    ("tasks", "shame_logged", "INTEGER DEFAULT 0"),
    ("tasks", "verifier_id", "TEXT"),
    ("tasks", "verified_at", "TEXT"),
    ("tasks", "verified_by", "TEXT"),
    ("member_activity", "on_time_tasks", "INTEGER DEFAULT 0"),
    ("member_activity", "current_streak", "INTEGER DEFAULT 0"),
    ("member_activity", "best_streak", "INTEGER DEFAULT 0"),
]