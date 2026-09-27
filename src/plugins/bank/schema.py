"""Bank plugin schema - accounts and append-only transaction ledger."""

BANK_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS bank_accounts (
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        balance INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, user_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bank_transactions (
        tx_id TEXT PRIMARY KEY,
        guild_id TEXT NOT NULL,
        from_user TEXT NOT NULL,
        to_user TEXT NOT NULL,
        amount INTEGER NOT NULL,
        reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bank_tx_guild_time
    ON bank_transactions (guild_id, created_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_bank_tx_users
    ON bank_transactions (guild_id, from_user, to_user)
    """,
    """
    CREATE TABLE IF NOT EXISTS bank_settings (
        guild_id TEXT PRIMARY KEY,
        tax_rate_bps INTEGER NOT NULL DEFAULT 0
    )
    """,
]