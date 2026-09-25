"""
Activity tracking and DM file deliverable vault Cog interface.

What it does:
- Listens to server messages and increments activity counts.
- Catches DM file attachments, invokes VaultService, and provides verification receipts.

What it does NOT do:
- Does NOT execute direct filesystem writes or SQL queries.
"""

import logging
from datetime import datetime, timezone
import discord
from discord.ext import commands

from src.application.services.activity_service import ActivityService
from src.application.services.vault_service import VaultService
from src.interface.discord_formatters import build_vault_receipt_embed, COLOR_SUCCESS

logger = logging.getLogger("interface.cogs.tracker")

class TrackerCog(commands.Cog, name="Activity Tracker"):
    """Interface adapter for chat activity tracking and file deliverable submissions."""

    def __init__(
        self,
        bot: commands.Bot,
        activity_service: ActivityService,
        vault_service: VaultService
    ):
        self.bot = bot
        self.activity_service = activity_service
        self.vault_service = vault_service

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        # 1. Track server message participation
        if message.guild:
            try:
                await self.activity_service.record_message(
                    guild_id=str(message.guild.id),
                    user_id=str(message.author.id)
                )
            except Exception as e:
                logger.error("Error recording message activity: %s", e)

        # 2. Track DM deliverable submissions
        elif isinstance(message.channel, discord.DMChannel) and message.attachments:
            await self._handle_dm_submission(message)

    async def _handle_dm_submission(self, message: discord.Message):
        user = message.author
        mutual_guilds = [g for g in self.bot.guilds if g.get_member(user.id)]
        primary_guild = mutual_guilds[0] if mutual_guilds else None
        guild_id = str(primary_guild.id) if primary_guild else None

        for attachment in message.attachments:
            try:
                content = await attachment.read()
                result = await self.vault_service.store_deliverable(
                    guild_id=guild_id,
                    user_id=str(user.id),
                    filename=attachment.filename,
                    content=content
                )

                # Send verification receipt in DM
                receipt = build_vault_receipt_embed(result, user.name)
                await message.channel.send(
                    content="✅ **Submission Verified and Secured!**",
                    embed=receipt
                )

                # Announce to #submissions channel in server if available
                if primary_guild:
                    sub_ch = discord.utils.get(primary_guild.text_channels, name="submissions")
                    if sub_ch:
                        announce_embed = discord.Embed(
                            title="📦 Verified Deliverable Submission",
                            description=f"{user.mention} submitted a verified project file.",
                            color=COLOR_SUCCESS,
                            timestamp=datetime.now(timezone.utc)
                        )
                        announce_embed.add_field(name="📄 File", value=f"`{result.stored_filename}`", inline=True)
                        announce_embed.add_field(name="🔐 Hash", value=f"`{result.file_hash[:16]}...`", inline=True)
                        await sub_ch.send(embed=announce_embed)

            except Exception as e:
                logger.error("Failed to store DM submission from %s: %s", user.id, e, exc_info=True)
                await message.channel.send("❌ Error securing your file submission. Please try again.")
