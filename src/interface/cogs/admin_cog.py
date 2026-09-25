"""
Administration and setup Discord Cog interface.

What it does:
- Ensures presence of #tasks, #deadlines, and #submissions channels on guild join.
- Exposes /setup and /guide slash commands.

What it does NOT do:
- Does NOT execute business logic or domain calculations.
"""

import logging
from typing import List
import discord
from discord import app_commands
from discord.ext import commands

from src.interface.discord_formatters import COLOR_PRIMARY, COLOR_SUCCESS

logger = logging.getLogger("interface.cogs.admin")

class AdminCog(commands.Cog, name="Administration"):
    """Interface adapter for server channel setup and bot command guides."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _ensure_channels(self, guild: discord.Guild) -> List[discord.TextChannel]:
        channel_configs = [
            ("tasks", "Group task ledger and deliverables tracking."),
            ("deadlines", "Project milestones and live countdown timers."),
            ("submissions", "Verified deliverable submission vault announcements.")
        ]
        created_or_found = []
        for name, topic in channel_configs:
            ch = discord.utils.get(guild.text_channels, name=name)
            if not ch and guild.me.guild_permissions.manage_channels:
                try:
                    ch = await guild.create_text_channel(name=name, topic=topic)
                except Exception as e:
                    logger.warning("Could not auto-create #%s in guild %s: %s", name, guild.name, e)
            if ch:
                created_or_found.append(ch)
        return created_or_found

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Auto-provisions group work channels on joining a new server."""
        logger.info("Bot joined guild %s (%s). Provisioning channels...", guild.name, guild.id)
        await self._ensure_channels(guild)

    @app_commands.command(name="setup", description="Verify and create #tasks, #deadlines, and #submissions channels")
    @app_commands.default_permissions(manage_channels=True)
    async def setup_channels(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be run in a server.", ephemeral=True)
            return

        channels = await self._ensure_channels(guild)
        ch_list = ", ".join(c.mention for c in channels) if channels else "None"

        embed = discord.Embed(
            title="🛠️ Group Accountability Channels",
            description=f"Verified channels:\n\n{ch_list}",
            color=COLOR_SUCCESS
        )
        embed.add_field(
            name="Available Features",
            value=(
                "• `/task add` — Assign tasks with auto-reminders\n"
                "• `/deadline add` — Live pinned countdowns\n"
                "• `/submit` — Submit deliverables with cryptographic verification\n"
                "• `/report` — Anti-free-riding contribution scoreboard"
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="guide", description="View bot command cheat sheet and group collaboration guide")
    async def guide(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Group Accountability Bot Guide",
            description="Designed to eliminate free-riding and maintain transparent collaboration in student teams.",
            color=COLOR_PRIMARY
        )
        embed.add_field(
            name="1. 📋 Task Ledger",
            value=(
                "`/task add <desc> <@member> <YYYY-MM-DD>` — Assign deliverable task\n"
                "`/task complete <TASK-ID>` — Mark completed\n"
                "`/task list` — View pending tasks"
            ),
            inline=False
        )
        embed.add_field(
            name="2. 🎯 Deadlines & Alerts",
            value=(
                "`/deadline add <name> <YYYY-MM-DD HH:MM>` — Pin live countdown in `#deadlines`\n"
                "`/deadline list` — View active milestones\n"
                "`/deadline complete <DL-ID>` — Archive finished deadline"
            ),
            inline=False
        )
        embed.add_field(
            name="3. 📊 Anti-Free-Riding Reports",
            value=(
                "`/report` — View team contribution ranking\n"
                "`/report <@member>` — View individual completion rate and message volume"
            ),
            inline=False
        )
        embed.add_field(
            name="4. 📥 File Deliverable Vault",
            value="`/submit file:<attachment> [notes:<text>]` — Uploads and verifies project deliverables with SHA-256 hash logging, transparently posted to `#submissions`.",
            inline=False
        )
        embed.set_footer(text="Automated alerts: T-24h & T-1h for tasks; T-72h, T-24h & T-6h for milestones.")
        await interaction.response.send_message(embed=embed)
