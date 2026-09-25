import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from bot.database import db_instance
from bot.utils.embeds import (
    create_member_report_embed,
    create_guild_report_embed
)

logger = logging.getLogger("bot.cogs.reports")

class ContributionReportCog(commands.Cog, name="Contribution Reports"):
    """Generates contribution metrics, anti-free-riding reports, and team summaries."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(
        name="report",
        description="View team contribution metrics, tasks completed, messages, and file submissions"
    )
    @app_commands.describe(member="Optional: Select a specific team member to view their individual stats")
    async def report(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        await interaction.response.defer()

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command must be executed within a server.", ephemeral=True)
            return

        guild_id = str(guild.id)

        # Individual member report
        if member:
            stats = await db_instance.get_member_stats(guild_id, str(member.id))
            embed = create_member_report_embed(member, stats)
            await interaction.followup.send(embed=embed)
            return

        # Overall group summary report
        leaderboard_data = await db_instance.get_guild_activity_report(guild_id)
        embed = create_guild_report_embed(guild.name, leaderboard_data, self.bot)
        await interaction.followup.send(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(ContributionReportCog(bot))
