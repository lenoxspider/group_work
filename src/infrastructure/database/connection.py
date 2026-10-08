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

from src.infrastructure.database.sqlite import connect
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
        async with connect(self.db_path) as db:
            # WAL is stored in the database header, so setting it once here
            # covers every later connection: readers stop blocking the writer
            # and vice versa. The default journal mode is "delete", under which
            # a single write blocks the seven background loops sharing this
            # file. Connections already wait 5s for a lock (aiosqlite inherits
            # sqlite3's timeout=5.0), so WAL is the real change here.
            try:
                rows = await db.execute_fetchall("PRAGMA journal_mode=WAL")
                logger.info("SQLite journal_mode: %s", rows[0][0] if rows else "unknown")
            except Exception as exc:
                # Not fatal - the filesystem may not support shared memory - but
                # it should never be silent, since concurrency degrades without it.
                logger.warning("Could not enable WAL journal mode: %s", exc)

            for plugin_name, ddl_list in self._plugin_schemas.items():
                for ddl in ddl_list:
                    await db.execute(ddl)
                logger.info("Plugin schema applied: %s", plugin_name)

            for plugin_name, migrations in self._plugin_migrations.items():
                for table, col, col_type in migrations:
                    try:
                        await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {col_type}")
                        logger.info("Migration applied: %s.%s", table, col)
                    except Exception as exc:
                        # Re-running an applied migration is normal and stays
                        # quiet. Everything else used to vanish here and resurface
                        # much later as a baffling "no such column".
                        if "duplicate column name" in str(exc).lower():
                            continue
                        logger.error("Migration failed for %s.%s: %s", table, col, exc)

            await db.commit()
            logger.info("SQLite schema initialized successfully at %s", self.db_path)