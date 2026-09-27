"""Games plugin schema - events, event-scoped players, and votes."""

GAMES_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS games_events (
        event_id TEXT PRIMARY KEY,
        guild_id TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'REGISTERING',
        pot_amount INTEGER NOT NULL DEFAULT 0,
        current_game_index INTEGER NOT NULL DEFAULT 0,
        entry_fee INTEGER NOT NULL DEFAULT 0,
        winner_id TEXT,
        started_at TEXT,
        concluded_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS games_players (
        guild_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        player_number TEXT NOT NULL,
        is_alive INTEGER DEFAULT 1,
        survival_streak INTEGER DEFAULT 0,
        elimination_reason TEXT,
        eliminated_at TEXT,
        PRIMARY KEY (guild_id, event_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS games_votes (
        guild_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        choice TEXT NOT NULL,
        voted_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, event_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS games_movement_anomalies (
        guild_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        occurred_at TEXT NOT NULL,
        reason TEXT NOT NULL
    )
    """,
]