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

from src.application.services.squid_service import SquidService
from src.application.dtos.squid_dtos import RedLightMoveDTO
from src.domain.interfaces.audio_deliverer import AudioDeliverer
from src.domain.errors import AppError

logger = logging.getLogger("interface.cogs.move_command")

class MoveCommandCog(commands.Cog, name="Movement"):
    """Dedicated cog for the /move command in Red Light Green Light."""

    def __init__(
        self,
        bot: commands.Bot,
        squid_service: SquidService,
        audio_deliverer: AudioDeliverer
    ):
        self.bot = bot
        self.squid_service = squid_service
        self.audio_deliverer = audio_deliverer

    @app_commands.command(name="move", description="Take steps in Red Light Green Light (Safe only during Green Light!)")
    @app_commands.checks.cooldown(1, 1.0, key=lambda i: (i.guild_id, i.user.id))
    async def move(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        dto = RedLightMoveDTO(guild_id=str(interaction.guild_id), user_id=str(interaction.user.id))
        try:
            res = await self.squid_service.process_move(dto)
            if not res.survived:
                # Role swap: Player -> Spectator
                if interaction.guild and isinstance(interaction.user, discord.Member):
                    p_role = discord.utils.get(interaction.guild.roles, name="Player")
                    s_role = discord.utils.get(interaction.guild.roles, name="Spectator")
                    if p_role and p_role in interaction.user.roles:
                        await interaction.user.remove_roles(p_role, reason="Eliminated in Red Light Green Light")
                    if s_role and s_role not in interaction.user.roles:
                        await interaction.user.add_roles(s_role, reason="Moved to Spectators deck")

                embed = discord.Embed(
                    title="💀 SQUID GAME • ELIMINATION CONFIRMED",
                    description=f"🚨 **`{res.player_number}` (<@{res.user_id}>) MOVED DURING RED LIGHT!**\nYou have been moved to the Spectators lounge.",
                    color=discord.Color.from_rgb(255, 0, 144)
                )
                if interaction.user and interaction.user.display_avatar:
                    embed.set_thumbnail(url=interaction.user.display_avatar.url)

                if res.audio_bytes:
                    await self.audio_deliverer.deliver(interaction, res.audio_bytes, "eliminated.wav", embed=embed)
                else:
                    await interaction.followup.send(embed=embed, ephemeral=True)
            else:
                badge = "🏁" if res.is_finished else "🏃"
                await interaction.followup.send(f"{badge} **Player {res.player_number}**: {res.status_message}", ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"⚠️ {e.message}", ephemeral=True)
