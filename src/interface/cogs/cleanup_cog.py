"""
Channel message purge and maintenance Cog interface.

What it does:
- Provides /cleanup command for bulk purging old or test messages in a channel.
- Provides /clean_arena command for sweeping #game-hub and #spectators.
- Enforces Discord rate limits and permission checks (manage_messages).

What it does NOT do:
- Does NOT delete messages older than 14 days without individual fallback.
- Does NOT execute raw database modifications.
"""

import logging
from typing import Optional, Literal
import discord
from discord import app_commands
from discord.ext import commands

from src.interface.channel_router import ChannelRouter

logger = logging.getLogger("interface.cogs.cleanup")

class CleanupCog(commands.Cog, name="Maintenance"):
    """Interface adapter for administrative channel message cleaning and maintenance."""

    def __init__(self, bot: commands.Bot, channel_router: ChannelRouter):
        self.bot = bot
        self.channel_router = channel_router

    @app_commands.command(
        name="cleanup",
        description="Admin maintenance: bulk delete recent messages in this channel or a target channel"
    )
    @app_commands.describe(
        amount="Number of messages to scan and delete (1 to 100)",
        filter_mode="all (delete all messages) or bot_only (delete only bot responses)",
        channel="Optional target channel (defaults to current channel)"
    )
    @app_commands.default_permissions(manage_messages=True)
    async def cleanup(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 50,
        filter_mode: Literal["all", "bot_only"] = "all",
        channel: Optional[discord.TextChannel] = None
    ) -> None:
        """Purges messages matching the given filter up to the specified amount."""
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        target_ch = channel or interaction.channel
        if not isinstance(target_ch, discord.TextChannel):
            await interaction.followup.send("❌ Cleanup can only be executed in text channels.", ephemeral=True)
            return

        # Check bot permissions in target channel
        if not target_ch.permissions_for(target_ch.guild.me).manage_messages:
            await interaction.followup.send(
                f"❌ Bot lacks `Manage Messages` permission in {target_ch.mention}.",
                ephemeral=True
            )
            return

        check_fn = (lambda m: m.author.id == self.bot.user.id) if filter_mode == "bot_only" else (lambda m: True)

        try:
            deleted = await target_ch.purge(limit=amount, check=check_fn)
            count = len(deleted)
            mode_desc = "bot message(s)" if filter_mode == "bot_only" else "message(s)"
            embed = discord.Embed(
                title="🧹 Channel Cleanup Completed",
                description=f"Successfully purged **{count}** {mode_desc} from {target_ch.mention}.",
                color=discord.Color.from_rgb(3, 122, 118)
            )
            embed.set_footer(text="Admin Maintenance • Messages older than 14 days were skipped by Discord API")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error("Error during channel purge in %s: %s", target_ch.id, e, exc_info=True)
            await interaction.followup.send(f"❌ Failed to purge messages: {e}", ephemeral=True)

    @app_commands.command(
        name="clean_arena",
        description="Admin maintenance: sweep and clean #game-hub and #spectators channels"
    )
    @app_commands.describe(amount="Maximum messages to scan per arena channel (1 to 100)")
    @app_commands.default_permissions(manage_messages=True)
    async def clean_arena(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100] = 50
    ) -> None:
        """Sweeps and purges transitory test messages from #game-hub and #spectators."""
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        if not interaction.guild:
            await interaction.followup.send("❌ This command must be run inside a server.", ephemeral=True)
            return

        results = []
        for key in ["game-hub", "spectators"]:
            ch = await self.channel_router.resolve(interaction.guild, key)
            if ch and isinstance(ch, discord.TextChannel):
                if ch.permissions_for(interaction.guild.me).manage_messages:
                    try:
                        deleted = await ch.purge(limit=amount)
                        results.append(f"• {ch.mention}: **{len(deleted)}** messages purged")
                    except Exception as e:
                        results.append(f"• {ch.mention}: Failed ({e})")
                else:
                    results.append(f"• {ch.mention}: Lacks `Manage Messages` permission")

        summary = "\n".join(results) if results else "No arena channels resolved."
        embed = discord.Embed(
            title="🏟️ Arena Sweep Completed",
            description=f"Arena cleaning summary:\n{summary}",
            color=discord.Color.from_rgb(255, 0, 144)
        )
        embed.set_footer(text="Squid Game Arena Maintenance")
        await interaction.followup.send(embed=embed, ephemeral=True)

async def setup(bot: commands.Bot):
    # Cog mounted explicitly in bot.py
    pass
