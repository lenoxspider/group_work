"""
SQLite implementation of ChannelBindingRepository.

What it does:
- Persists and queries Discord snowflake IDs mapped to logical keys (e.g. 'tasks', 'game-hub').

What it does NOT do:
- Does NOT perform Discord gateway calls or business logic.
"""

from typing import Optional, Dict
import aiosqlite
from src.domain.entities.channel_binding import ChannelBinding
from src.domain.interfaces.channel_binding_repository import ChannelBindingRepository

class SQLiteChannelBindingRepository(ChannelBindingRepository):
    """aiosqlite-backed repository for persistent channel bindings."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def save_binding(self, binding: ChannelBinding) -> None:
        """Persists or updates a guild channel binding."""
        query = """
            INSERT INTO channel_bindings (guild_id, channel_key, channel_id, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id, channel_key) DO UPDATE SET
                channel_id = excluded.channel_id,
                updated_at = excluded.updated_at
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                query,
                (binding.guild_id, binding.channel_key, binding.channel_id, binding.updated_at.isoformat())
            )
            await db.commit()

    async def get_binding(self, guild_id: str, channel_key: str) -> Optional[str]:
        """Retrieves bound Discord channel snowflake ID for a key."""
        query = "SELECT channel_id FROM channel_bindings WHERE guild_id = ? AND channel_key = ?"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, (guild_id, channel_key)) as cursor:
                row = await cursor.fetchone()
                return str(row[0]) if row else None

    async def list_bindings(self, guild_id: str) -> Dict[str, str]:
        """Retrieves all logical channel keys and their bound Discord channel IDs in a guild."""
        query = "SELECT channel_key, channel_id FROM channel_bindings WHERE guild_id = ?"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, (guild_id,)) as cursor:
                rows = await cursor.fetchall()
                return {row[0]: str(row[1]) for row in rows}

    async def delete_binding(self, guild_id: str, channel_key: str) -> None:
        """Removes a binding when a channel is retired."""
        query = "DELETE FROM channel_bindings WHERE guild_id = ? AND channel_key = ?"
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, (guild_id, channel_key))
            await db.commit()
