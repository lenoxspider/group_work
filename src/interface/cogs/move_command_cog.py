"""
Top-level /move slash command cog for Red Light Green Light gameplay.

What it does:
- Handles player movement requests during active matches.
- Applies per-player command cooldown and latency grace evaluations.
- Swaps eliminated players to Spectator role atomically.

What it does NOT do:
- Does NOT manage guild-wide game cycles or voice line synthesis.
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

from typing import Optional
from src.application.services.squid_service import SquidService
from src.domain.interfaces.audio_deliverer import AudioDeliverer
from src.interface.channel_router import ChannelRouter
from src.interface.squid_formatters import build_ephemeral_move_feedback
from src.domain.errors import AppError

logger = logging.getLogger("interface.cogs.move_command")

class MoveCommandCog(commands.Cog, name="Movement"):
    """Dedicated cog for the /move command in Red Light Green Light."""

    def __init__(
        self,
        bot: commands.Bot,
        squid_service: SquidService,
        audio_deliverer: AudioDeliverer,
        channel_router: Optional[ChannelRouter] = None
    ):
        self.bot = bot
        self.squid_service = squid_service
        self.audio_deliverer = audio_deliverer
        self.channel_router = channel_router

    @app_commands.command(name="move", description="Take steps in Red Light Green Light (Safe only during Green Light!)")
    @app_commands.checks.cooldown(1, 0.5, key=lambda i: (i.guild_id, i.user.id))
    async def move(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        if self.channel_router and interaction.guild:
            hub = await self.channel_router.resolve(interaction.guild, "game-hub")
            if hub and interaction.channel_id != hub.id:
                await interaction.followup.send(
                    f"⚠️ **Wrong Arena:** You can only `/move` inside {hub.mention}!",
                    ephemeral=True
                )
                return

        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        try:
            res = await self.squid_service.handle_move(guild_id, user_id)
            if not res.survived and interaction.guild and isinstance(interaction.user, discord.Member):
                p_role = discord.utils.get(interaction.guild.roles, name="Player")
                s_role = discord.utils.get(interaction.guild.roles, name="Spectator")
                if p_role and p_role in interaction.user.roles:
                    await interaction.user.remove_roles(p_role, reason="Eliminated in Red Light Green Light")
                if s_role and s_role not in interaction.user.roles:
                    await interaction.user.add_roles(s_role, reason="Moved to Spectators deck")

            feedback = build_ephemeral_move_feedback(res)
            await interaction.followup.send(feedback, ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"⚠️ {e.message}", ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ {str(e)}", ephemeral=True)
