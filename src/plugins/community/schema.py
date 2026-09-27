"""Community plugin schema - the member registry and the tribunal docket."""

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
    """
    CREATE TABLE IF NOT EXISTS court_cases (
        case_id TEXT PRIMARY KEY,
        guild_id TEXT NOT NULL,
        accuser_id TEXT NOT NULL,
        accused_id TEXT NOT NULL,
        law_id TEXT NOT NULL,
        evidence TEXT NOT NULL DEFAULT '',
        defense TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'OPEN',
        guilty_votes TEXT NOT NULL DEFAULT '',
        innocent_votes TEXT NOT NULL DEFAULT '',
        round INTEGER NOT NULL DEFAULT 1,
        message_id TEXT,
        channel_id TEXT,
        sentenced INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        opened_at TEXT NOT NULL,
        resolved_at TEXT
    )
    """,
]