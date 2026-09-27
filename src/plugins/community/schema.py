"""Community plugin schema - the member registry."""

COMMUNITY_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS member_registry (
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'catizen',
        intro_task_id TEXT,
        intro_done INTEGER DEFAULT 0,
        joined_at TEXT NOT NULL,
        signed_at TEXT,
        PRIMARY KEY (guild_id, user_id)
    )
    """,
]