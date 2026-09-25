"""
Contribution report Discord Cog interface.

What it does:
- Exposes /report slash command for individual scorecards and team standings.
- Serializes report DTOs into visual embeds with progress bars.

What it does NOT do:
- Does NOT calculate contribution weights or query database directly.
"""

from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.application.services.activity_service import ActivityService
from src.interface.discord_formatters import (
    build_member_report_embed,
    build_guild_report_embed
)

class ReportsCog(commands.Cog, name="Contribution Reports"):
    """Interface adapter for anti-free-riding contribution reports."""

    def __init__(self, bot: commands.Bot, activity_service: ActivityService):
        self.bot = bot
        self.service = activity_service

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
        if member:
            dto = await self.service.get_member_report(guild_id, str(member.id))
            embed = build_member_report_embed(dto, member)
            await interaction.followup.send(embed=embed)
            return

        guild_dto = await self.service.get_guild_report(guild_id)
        embed = build_guild_report_embed(guild_dto, guild)
        await interaction.followup.send(embed=embed)
