"""Pulse plugin schema - pacing state."""

PULSE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS pulse_state (
        guild_id TEXT PRIMARY KEY,
        last_fired TEXT
    )
    """,
]