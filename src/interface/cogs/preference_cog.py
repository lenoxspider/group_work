"""
Member preference Discord slash commands.

What it does:
- Exposes /timezone slash commands for student timezone and quiet hours.
- Handles user input, calls PreferenceService, and formats embeds.

What it does NOT do:
- Does NOT execute database queries or SQL directly.
- Does NOT compute quiet hours logic.
"""

import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.application.services.preference_service import PreferenceService
from src.application.dtos.preference_dtos import SetTimezoneDTO, SetQuietHoursDTO
from src.interface.discord_formatters import build_preference_embed
from src.domain.errors import AppError

logger = logging.getLogger("interface.cogs.preference")

class PreferenceCog(commands.GroupCog, group_name="timezone"):
    """Slash commands for managing member timezone and quiet hours (DND)."""

    def __init__(self, bot: commands.Bot, preference_service: PreferenceService):
        self.bot = bot
        self.service = preference_service
        super().__init__()

    @app_commands.command(name="set", description="Set your local IANA timezone (e.g. America/New_York, UTC, Europe/London)")
    @app_commands.describe(timezone="Valid IANA timezone identifier (e.g. America/New_York, UTC, Europe/London, Asia/Tokyo)")
    async def set_timezone(self, interaction: discord.Interaction, timezone: str):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        dto = SetTimezoneDTO(
            guild_id=str(interaction.guild_id),
            user_id=str(interaction.user.id),
            timezone_name=timezone.strip()
        )
        try:
            result = await self.service.set_timezone(dto)
            embed = build_preference_embed(result, interaction.user)  # type: ignore[arg-type]
            await interaction.followup.send(
                f"✅ Timezone set to **{result.timezone_name}**.",
                embed=embed,
                ephemeral=True
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @app_commands.command(name="quiet", description="Set quiet hours window (DND) when you do not want reminder DMs (0-23)")
    @app_commands.describe(
        start_hour="Starting hour (0-23 in your local time, e.g. 23 for 11 PM)",
        end_hour="Ending hour (0-23 in your local time, e.g. 8 for 8 AM)"
    )
    async def set_quiet_hours(self, interaction: discord.Interaction, start_hour: int, end_hour: int):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        dto = SetQuietHoursDTO(
            guild_id=str(interaction.guild_id),
            user_id=str(interaction.user.id),
            start_hour=start_hour,
            end_hour=end_hour
        )
        try:
            result = await self.service.set_quiet_hours(dto)
            embed = build_preference_embed(result, interaction.user)  # type: ignore[arg-type]
            await interaction.followup.send(
                f"✅ Quiet hours updated to **{result.quiet_hours_start:02d}:00 – {result.quiet_hours_end:02d}:00**.",
                embed=embed,
                ephemeral=True
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @app_commands.command(name="view", description="View your current timezone and quiet hours settings")
    async def view_preferences(self, interaction: discord.Interaction):
        if not interaction.guild:
            await interaction.response.send_message("❌ Command must be used in a server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        try:
            result = await self.service.get_preference(str(interaction.guild_id), str(interaction.user.id))
            embed = build_preference_embed(result, interaction.user)  # type: ignore[arg-type]
            await interaction.followup.send(embed=embed, ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

async def setup(bot: commands.Bot):
    # Cog is registered explicitly in bot.py setup_hook
    pass
