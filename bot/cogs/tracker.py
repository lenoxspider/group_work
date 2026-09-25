import os
import io
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Optional
import discord
from discord.ext import commands

from bot.database import db_instance
from bot.config import UPLOADS_DIR, SUBMISSIONS_CHANNEL_NAME
from bot.utils.helpers import compute_file_hash, sanitize_filename, generate_short_id
from bot.utils.embeds import create_file_submission_embed, COLOR_SUCCESS

logger = logging.getLogger("bot.cogs.tracker")

class ActivityTrackerCog(commands.Cog, name="Activity Tracker"):
    """Tracks chat messages and manages DM file deliverable submissions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Ignore messages from bots
        if message.author.bot:
            return

        # 1. Server Channel Message Activity Tracking
        if message.guild:
            try:
                await db_instance.increment_message_count(
                    guild_id=str(message.guild.id),
                    user_id=str(message.author.id)
                )
            except Exception as e:
                logger.error(f"Error updating message activity: {e}")

        # 2. DM File Submission Vault
        elif isinstance(message.channel, discord.DMChannel):
            if message.attachments:
                await self.handle_dm_file_submission(message)

    async def handle_dm_file_submission(self, message: discord.Message):
        """Processes file attachments sent directly to the bot in DMs."""
        user = message.author
        date_str = datetime.now(timezone.utc).strftime("%Y%m%d")

        # Find which mutual guilds the user shares with the bot
        mutual_guilds = [g for g in self.bot.guilds if g.get_member(user.id)]
        primary_guild = mutual_guilds[0] if mutual_guilds else None

        for attachment in message.attachments:
            try:
                # Read file bytes
                file_bytes = await attachment.read()
                file_hash = compute_file_hash(file_bytes)
                short_hash = file_hash[:8]
                file_size = len(file_bytes)

                # Format filename: draft_v1_YYYYMMDD_<hash>.<ext>
                original_name = sanitize_filename(attachment.filename)
                ext = Path(original_name).suffix or ".bin"
                stem = Path(original_name).stem
                stored_filename = f"{stem}_{date_str}_{short_hash}{ext}"
                target_path = os.path.join(UPLOADS_DIR, stored_filename)

                # Save file to disk
                with open(target_path, "wb") as f:
                    f.write(file_bytes)

                submission_id = generate_short_id("SUB")

                # Record in database
                await db_instance.log_file_submission(
                    submission_id=submission_id,
                    user_id=str(user.id),
                    original_filename=attachment.filename,
                    stored_filename=stored_filename,
                    file_hash=file_hash,
                    file_size=file_size,
                    guild_id=str(primary_guild.id) if primary_guild else None
                )

                # Send verification receipt embed in DM
                receipt_embed = create_file_submission_embed(
                    original_filename=attachment.filename,
                    stored_name=stored_filename,
                    file_hash=file_hash,
                    file_size=file_size,
                    member=user
                )
                await message.channel.send(
                    content=f"✅ **Submission Confirmed!** Your file has been securely archived.",
                    embed=receipt_embed
                )

                # If connected to a guild with a #submissions channel, broadcast notification
                if primary_guild:
                    for ch in primary_guild.text_channels:
                        if ch.name.lower() == SUBMISSIONS_CHANNEL_NAME.lower():
                            announcement_embed = discord.Embed(
                                title="📦 New Deliverable Vault Submission",
                                description=f"{user.mention} submitted a verified file.",
                                color=COLOR_SUCCESS,
                                timestamp=datetime.now(timezone.utc)
                            )
                            announcement_embed.add_field(name="📄 File", value=f"`{stored_filename}`", inline=True)
                            announcement_embed.add_field(name="🔐 Hash (SHA-256)", value=f"`{file_hash[:16]}...`", inline=True)
                            await ch.send(embed=announcement_embed)
                            break

                logger.info(f"Logged submission {submission_id} ({stored_filename}) from user {user.name}")

            except Exception as e:
                logger.error(f"Error processing DM submission from {user.id}: {e}", exc_info=True)
                await message.channel.send("❌ There was an error storing your submission. Please try again.")

async def setup(bot: commands.Bot):
    await bot.add_cog(ActivityTrackerCog(bot))
