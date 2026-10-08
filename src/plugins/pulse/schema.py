"""Pulse plugin schema - pacing state."""

PULSE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS pulse_state (
        guild_id TEXT PRIMARY KEY,
        last_fired TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pulse_active (
        guild_id TEXT PRIMARY KEY,
        channel_id TEXT NOT NULL,
        message_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        label TEXT NOT NULL,
        answer TEXT NOT NULL DEFAULT '',
        mode TEXT NOT NULL,
        started_at TEXT NOT NULL,
        accept TEXT NOT NULL DEFAULT '[]',
        vote_options TEXT NOT NULL DEFAULT '{}',
        timeout_seconds INTEGER NOT NULL DEFAULT 90,
        data TEXT NOT NULL DEFAULT '{}'
    )
    """,
]