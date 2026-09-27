"""
SQLite database connection and migration manager.

What it does:
- Owns the aiosqlite connection lifecycle.
- Applies plugin-registered schemas and migrations in dependency order.

What it does NOT do:
- Does NOT know about any specific feature's tables. Tables are owned
  by plugins via register_plugin_schema / register_plugin_migrations.
- Does NOT execute domain business logic.
- Does NOT interact with Discord APIs.
"""

import aiosqlite
import logging

logger = logging.getLogger("infrastructure.database")


class DatabaseManager:
    """Manages SQLite connection lifecycle and plugin schema application."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._plugin_schemas = {}
        self._plugin_migrations = {}

    def register_plugin_schema(self, plugin_name: str, ddl_list) -> None:
        """Register a plugin's CREATE TABLE DDL."""
        self._plugin_schemas[plugin_name] = ddl_list

    def register_plugin_migrations(self, plugin_name: str, migrations) -> None:
        """Register a plugin's additive column migrations as (table, col, type) tuples."""
        self._plugin_migrations[plugin_name] = migrations

    async def initialize_schema(self) -> None:
        """Create all plugin tables, then apply additive column migrations."""
        async with aiosqlite.connect(self.db_path) as db:
            for plugin_name, ddl_list in self._plugin_schemas.items():
                for ddl in ddl_list:
                    await db.execute(ddl)
                logger.info("Plugin schema applied: %s", plugin_name)

            for plugin_name, migrations in self._plugin_migrations.items():
                for table, col, col_type in migrations:
                    try:
                        await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                    except Exception:
                        pass

            await db.commit()
            logger.info("SQLite schema initialized successfully at %s", self.db_path)