"""Offices plugin schema - one holder per office per guild."""

OFFICES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS offices (
        guild_id TEXT NOT NULL,
        office TEXT NOT NULL,
        user_id TEXT NOT NULL,
        appointed_at TEXT NOT NULL,
        appointed_by TEXT,
        PRIMARY KEY (guild_id, office)
    )
    """,
]
