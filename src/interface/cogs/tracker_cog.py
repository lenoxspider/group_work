"""
Activity tracking and deliverable vault submission Cog interface.

What it does:
- Listens to server messages and increments activity counts.
- Exposes /submit slash command for in-server file uploads with SHA-256 verification.

What it does NOT do:
- Does NOT listen to private DMs or execute direct disk/SQL queries.
"""

import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.application.services.activity_service import ActivityService
from src.application.services.vault_service import VaultService
from src.interface.channel_router import ChannelRouter
from src.domain.errors import AppError
from src.interface.discord_formatters import build_vault_receipt_embed

logger = logging.getLogger("interface.cogs.tracker")

MAX_FILE_SIZE_BYTES = 25 * 1024 * 1024  # 25 MB

class TrackerCog(commands.Cog, name="Activity Tracker"):
    """Interface adapter for chat activity tracking and in-server file submissions."""

    def __init__(
        self,
        bot: commands.Bot,
        activity_service: ActivityService,
        vault_service: VaultService,
        channel_router: Optional[ChannelRouter] = None
    ):
        self.bot = bot
        self.activity_service = activity_service
        self.vault_service = vault_service
        self.channel_router = channel_router

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Tracks messages sent within server channels."""
        if message.author.bot or not message.guild:
            return

        try:
            await self.activity_service.record_message(
                guild_id=str(message.guild.id),
                user_id=str(message.author.id)
            )
        except Exception as e:
            logger.error("Error recording message activity: %s", e)

    @app_commands.command(
        name="submit",
        description="Submit a project deliverable file with verification and hash logging"
    )
    @app_commands.describe(
        file="The deliverable file to submit (e.g. PDF, docx, code, zip)",
        notes="Optional notes or description regarding this submission"
    )
    async def submit_deliverable(
        self,
        interaction: discord.Interaction,
        file: discord.Attachment,
        notes: Optional[str] = None
    ):
        await interaction.response.defer()

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Submissions must be made inside your project server.", ephemeral=True)
            return

        if file.size > MAX_FILE_SIZE_BYTES:
            await interaction.followup.send(
                f"❌ File size exceeds the maximum limit of {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB.",
                ephemeral=True
            )
            return

        try:
            content = await file.read()
            result = await self.vault_service.store_deliverable(
                guild_id=str(guild.id),
                user_id=str(interaction.user.id),
                filename=file.filename,
                content=content,
                notes=notes
            )

            receipt_embed = build_vault_receipt_embed(result, interaction.user.display_name)

            # Locate #submissions channel via ChannelRouter
            submissions_ch = await self.channel_router.get(guild, "submissions") if self.channel_router else discord.utils.get(guild.text_channels, name="submissions")
            jump_url_field = None
            if submissions_ch and submissions_ch.id != interaction.channel_id:
                posted_msg = await submissions_ch.send(
                    content=f"📥 **New Deliverable Submitted by {interaction.user.mention}:**",
                    embed=receipt_embed
                )
                jump_url_field = posted_msg.jump_url

            if jump_url_field:
                receipt_embed.add_field(name="🔗 Permanent Jump URL", value=f"[View Audit Receipt]({jump_url_field})", inline=False)

            await interaction.followup.send(
                content=f"✅ **Deliverable submitted successfully!** Logged to #{submissions_ch.name if submissions_ch else 'current channel'}.",
                embed=receipt_embed
            )
        except discord.HTTPException as e:
            if e.status == 413:
                await interaction.followup.send("❌ **File Too Large**: Discord rejected the file upload (exceeds server limit). Please compress the deliverable.", ephemeral=True)
                return
            logger.error("HTTP error storing submission: %s", e)
            await interaction.followup.send("❌ Network error while uploading deliverable.", ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)
        except Exception as e:
            logger.error("Failed to store submission: %s", e, exc_info=True)
            await interaction.followup.send("❌ An unexpected error occurred while saving your submission.", ephemeral=True)
