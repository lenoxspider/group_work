"""Chronicle plugin schema - the recorded history."""

CHRONICLE_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS chronicle_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL,
        posted INTEGER NOT NULL DEFAULT 0
    )
    """,
]
