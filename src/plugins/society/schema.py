"""Society plugin schema - laws (constitution) and governance proposals."""

SOCIETY_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS laws (
        law_id TEXT PRIMARY KEY,
        guild_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        fine_amount INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS proposals (
        proposal_id TEXT PRIMARY KEY,
        guild_id TEXT NOT NULL,
        author_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        amount INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'OPEN',
        approvals TEXT NOT NULL DEFAULT '',
        rejections TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        resolved_at TEXT
    )
    """,
]