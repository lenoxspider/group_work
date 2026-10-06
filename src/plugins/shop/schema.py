"""Shop plugin schema - the purchase ledger."""

SHOP_SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS shop_purchases (
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        item_id TEXT NOT NULL,
        price INTEGER NOT NULL,
        role_id TEXT,
        bought_at TEXT NOT NULL,
        PRIMARY KEY (guild_id, user_id, item_id)
    )
    """,
]
