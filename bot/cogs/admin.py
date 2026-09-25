import logging
import discord
from discord import app_commands
from discord.ext import commands

from bot.config import TASKS_CHANNEL_NAME, DEADLINES_CHANNEL_NAME, SUBMISSIONS_CHANNEL_NAME
from bot.utils.helpers import get_or_create_channel
from bot.utils.embeds import COLOR_PRIMARY, COLOR_SUCCESS

logger = logging.getLogger("bot.cogs.admin")

class AdminCog(commands.Cog, name="Bot Administration"):
    """Handles channel setup, auto-creation on join, and guide commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def ensure_project_channels(self, guild: discord.Guild):
        """Creates or verifies the three primary group channels."""
        channels_info = [
            (TASKS_CHANNEL_NAME, "Group task ledger and real-time deliverables tracking."),
            (DEADLINES_CHANNEL_NAME, "Major project milestones, assignment due dates, and live countdowns."),
            (SUBMISSIONS_CHANNEL_NAME, "Verified file deliverable vault and receipts log.")
        ]
        created = []
        for name, topic in channels_info:
            ch = await get_or_create_channel(guild, name, topic=topic)
            if ch:
                created.append(ch)
        return created

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Automatically create #tasks, #deadlines, and #submissions when bot joins."""
        logger.info(f"Bot joined guild: {guild.name} ({guild.id}). Initializing channels...")
        try:
            await self.ensure_project_channels(guild)
        except Exception as e:
            logger.error(f"Error during auto channel creation on guild join: {e}")

    @app_commands.command(name="setup", description="Ensure #tasks, #deadlines, and #submissions channels are created")
    @app_commands.default_permissions(manage_channels=True)
    async def setup_channels(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command must be run inside a Discord server.", ephemeral=True)
            return

        channels = await self.ensure_project_channels(guild)
        channels_list = ", ".join(c.mention for c in channels)

        embed = discord.Embed(
            title="🛠️ Server Channels Initialized",
            description=f"Group accountability channels are verified and ready to use:\n\n{channels_list}",
            color=COLOR_SUCCESS
        )
        embed.add_field(
            name="Next Steps",
            value=(
                "• Use `/task add` to assign responsibilities\n"
                "• Use `/deadline add` to set milestones & countdowns\n"
                "• DM files directly to this bot to securely archive deliverables\n"
                "• Check team progress anytime with `/report`"
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="guide", description="Show Group Accountability Bot command reference and workflow guide")
    async def guide(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Group Accountability Bot Guide",
            description="Designed to eliminate free-riding and ensure smooth collaboration in group assignments.",
            color=COLOR_PRIMARY
        )
        embed.add_field(
            name="1. 📋 Task Ledger",
            value=(
                "`/task add <desc> <@member> <YYYY-MM-DD>` — Assign a task with automated reminders\n"
                "`/task complete <TASK-ID>` — Mark your task completed\n"
                "`/task list [@member]` — View active tasks"
            ),
            inline=False
        )
        embed.add_field(
            name="2. 🎯 Deadlines & Countdowns",
            value=(
                "`/deadline add <name> <YYYY-MM-DD HH:MM>` — Pin a milestone with live countdown in `#deadlines`\n"
                "`/deadline list` — Show all milestones\n"
                "`/deadline complete <DL-ID>` — Archive finished deadline"
            ),
            inline=False
        )
        embed.add_field(
            name="3. 📊 Contribution Reports & Anti-Free-Riding",
            value=(
                "`/report` — View team-wide contribution leaderboard\n"
                "`/report <@member>` — View individual task completion %, message volume, and deliverables"
            ),
            inline=False
        )
        embed.add_field(
            name="4. 📥 File Deliverable Vault",
            value="DM files (PDF, docx, code, zip) directly to this bot! The bot computes a SHA-256 hash, renames it with versioning, and logs it to your contribution score.",
            inline=False
        )
        embed.set_footer(text="Automated alerts are sent at T-24h & T-1h for tasks, and T-72h, T-24h & T-6h for milestones.")
        await interaction.response.send_message(embed=embed)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
