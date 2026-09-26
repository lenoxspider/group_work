"""
Centralized Discord channel router.

What it does:
- Resolves logical channel keys ('tasks', 'deadlines', 'submissions', 'wall-of-shame', 'game-hub', 'spectators', 'bot-log')
  using a robust 4-tier fallback strategy:
  1. Persisted SQLite Snowflake ID binding.
  2. Dynamic name lookup with auto-healing SQLite persistence.
  3. Category scan ('TOVARISHCH').
  4. System channel / Owner DM fallback with failure logging.

What it does NOT do:
- Does NOT execute direct raw SQL (delegates to ChannelBindingRepository).
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict
import discord
from src.domain.entities.channel_binding import ChannelBinding
from src.domain.interfaces.channel_binding_repository import ChannelBindingRepository

logger = logging.getLogger("interface.channel_router")

class ChannelRouter:
    """Centralized resolver preventing silent alert drops across renames and reboots."""

    CATEGORY_NAME = "TOVARISHCH"

    def __init__(
        self,
        bot: discord.Client,
        binding_repo: ChannelBindingRepository
    ):
        self.bot = bot
        self.binding_repo = binding_repo
        self.route_failures: Dict[str, int] = {}

    async def get(self, guild: discord.Guild, key: str) -> Optional[discord.TextChannel]:
        """
        Resolves a destination channel for a logical key using the 4-tier fallback chain.
        Never drops alerts silently.
        """
        guild_id = str(guild.id)

        # 1. Tier 1: Persisted Snowflake ID binding
        bound_id = await self.binding_repo.get_binding(guild_id, key)
        if bound_id:
            channel = self.bot.get_channel(int(bound_id))
            if not channel:
                try:
                    channel = await self.bot.fetch_channel(int(bound_id))
                except Exception:
                    channel = None
            if channel and isinstance(channel, discord.TextChannel):
                return channel
            logger.warning("Channel ID %s bound for key '%s' was deleted or inaccessible in guild %s.", bound_id, key, guild.id)

        # 2. Tier 2: Dynamic Name Lookup with Auto-Healing
        channel = discord.utils.get(guild.text_channels, name=key)
        if channel:
            logger.info("Auto-healing channel binding for key '%s' -> #%s (ID: %s)", key, channel.name, channel.id)
            await self.bind(guild_id, key, str(channel.id))
            return channel

        # 3. Tier 3: Category Scan
        category = discord.utils.get(guild.categories, name=self.CATEGORY_NAME)
        if category:
            for ch in category.text_channels:
                if key in ch.name.lower():
                    logger.info("Resolved key '%s' via category '%s' scan -> #%s", key, self.CATEGORY_NAME, ch.name)
                    await self.bind(guild_id, key, str(ch.id))
                    return ch

        # 4. Tier 4: Fallback to bot-log, system channel, or owner DM
        self._record_failure(guild_id, key)
        fallback = await self._resolve_emergency_fallback(guild, key)
        return fallback

    async def bind(self, guild_id: str, key: str, channel_id: str) -> None:
        """Persists a binding in SQLite."""
        binding = ChannelBinding(
            guild_id=guild_id,
            channel_key=key,
            channel_id=channel_id,
            updated_at=datetime.now(timezone.utc)
        )
        await self.binding_repo.save_binding(binding)

    async def resolve(self, guild: discord.Guild, key: str) -> Optional[discord.TextChannel]:
        """Alias for get() to resolve destination channels."""
        return await self.get(guild, key)

    async def bind_all(self, guild_id: str, bindings: Dict[str, str]) -> None:
        """Persists multiple key -> channel_id mappings."""
        now = datetime.now(timezone.utc)
        for key, ch_id in bindings.items():
            await self.binding_repo.save_binding(
                ChannelBinding(guild_id=guild_id, channel_key=key, channel_id=ch_id, updated_at=now)
            )

    def _record_failure(self, guild_id: str, key: str) -> None:
        fail_key = f"{guild_id}:{key}"
        self.route_failures[fail_key] = self.route_failures.get(fail_key, 0) + 1
        logger.error("CRITICAL: Route failure for key '%s' in guild %s (Total misses: %d)", key, guild_id, self.route_failures[fail_key])

    async def _resolve_emergency_fallback(self, guild: discord.Guild, missing_key: str) -> Optional[discord.TextChannel]:
        # Try bot-log
        bot_log_id = await self.binding_repo.get_binding(str(guild.id), "bot-log")
        if bot_log_id:
            bot_log = self.bot.get_channel(int(bot_log_id))
            if bot_log and isinstance(bot_log, discord.TextChannel):
                await bot_log.send(f"⚠️ **Routing Alert**: Channel for `{missing_key}` could not be resolved! Check server configuration.")
                return bot_log

        # Try system channel
        if guild.system_channel and guild.system_channel.permissions_for(guild.me).send_messages:
            return guild.system_channel

        # As last resort, try first available text channel where bot can write
        for ch in guild.text_channels:
            if ch.permissions_for(guild.me).send_messages:
                return ch

        return None
