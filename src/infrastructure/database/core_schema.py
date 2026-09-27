"""
Shared core infrastructure schema.

These tables belong to the shared runtime, not any single plugin.
Registered by the bot's composition root before plugin schemas.
"""

CORE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS channel_bindings (
        guild_id TEXT NOT NULL,
        channel_key TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, channel_key)
    )
    """,
]