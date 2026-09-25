"""
Administration, channel permission protection, and project lifecycle Cog interface.

What it does:
- Ensures presence of #tasks, #deadlines, and #submissions with read-only display protection for members.
- Exposes /setup, /guide, and /project lifecycle commands (status, finish/archive).

What it does NOT do:
- Does NOT execute direct raw SQL queries or domain business calculations.
"""

import logging
from datetime import datetime, timezone
from typing import List
import discord
from discord import app_commands
from discord.ext import commands

from src.application.services.project_service import ProjectService
from src.domain.errors import AppError
from src.interface.discord_formatters import (
    COLOR_PRIMARY,
    COLOR_SUCCESS,
    build_project_status_embed,
    build_project_archive_embed
)

logger = logging.getLogger("interface.cogs.admin")

class AdminCog(commands.Cog, name="Administration"):
    """Interface adapter for server setup, permission locking, and project lifecycle."""

    def __init__(self, bot: commands.Bot, project_service: ProjectService):
        self.bot = bot
        self.project_service = project_service

    project_group = app_commands.Group(name="project", description="Group project and sprint lifecycle commands")

    async def _ensure_channels_with_protection(self, guild: discord.Guild) -> List[discord.TextChannel]:
        """Creates or updates #tasks, #deadlines, and #submissions with read-only display protection."""
        channel_configs = [
            ("tasks", "📋 Group task ledger. Read-only display. Use /task to interact."),
            ("deadlines", "🎯 Major project milestones and live countdowns. Read-only display. Use /deadline to interact."),
            ("submissions", "📥 Verified deliverable submission vault. Read-only display. Use /submit to upload.")
        ]

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(
                view_channel=True,
                read_message_history=True,
                send_messages=False,
                add_reactions=True
            ),
            guild.me: discord.PermissionOverwrite(
                view_channel=True,
                send_messages=True,
                manage_messages=True,
                embed_links=True,
                attach_files=True,
                read_message_history=True
            )
        }

        created_or_found = []
        for name, topic in channel_configs:
            ch = discord.utils.get(guild.text_channels, name=name)
            if not ch and guild.me.guild_permissions.manage_channels:
                try:
                    ch = await guild.create_text_channel(name=name, topic=topic, overwrites=overwrites)
                except Exception as e:
                    logger.warning("Could not auto-create #%s in guild %s: %s", name, guild.name, e)
            elif ch and guild.me.guild_permissions.manage_channels:
                try:
                    await ch.edit(topic=topic, overwrites=overwrites)
                except Exception as e:
                    logger.warning("Could not enforce permission overwrites on #%s: %s", name, e)

            if ch:
                created_or_found.append(ch)
        return created_or_found

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Auto-provisions group work channels with read-only protection on joining a new server."""
        logger.info("Bot joined guild %s (%s). Provisioning protected channels...", guild.name, guild.id)
        await self._ensure_channels_with_protection(guild)

    @app_commands.command(
        name="setup",
        description="Verify and protect #tasks, #deadlines, and #submissions channels with read-only permissions"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def setup_channels(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be run in a server.", ephemeral=True)
            return

        channels = await self._ensure_channels_with_protection(guild)
        ch_list = ", ".join(c.mention for c in channels) if channels else "None"

        embed = discord.Embed(
            title="🛠️ Group Accountability Channels Configured",
            description=f"Channels verified with **Read-Only Display Protection**:\n\n{ch_list}",
            color=COLOR_SUCCESS
        )
        embed.add_field(
            name="🔒 Display Protection Active",
            value="Members can view all cards and countdowns cleanly without chat clutter. Use slash commands to interact.",
            inline=False
        )
        embed.add_field(
            name="Available Commands",
            value=(
                "• `/task add` — Assign tasks with auto-reminders\n"
                "• `/deadline add` — Live pinned countdowns\n"
                "• `/submit` — Submit deliverable files with SHA-256 verification\n"
                "• `/report` — Anti-free-riding contribution scoreboard\n"
                "• `/project status` — View overall project progress\n"
                "• `/project finish` — Conclude project and archive channels"
            ),
            inline=False
        )
        await interaction.followup.send(embed=embed)

    @project_group.command(name="status", description="View overall project progress, task health, and milestone countdown")
    async def project_status(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be run inside a server.", ephemeral=True)
            return

        status_dto = await self.project_service.get_project_status(str(guild.id))
        embed = build_project_status_embed(status_dto, guild.name)
        await interaction.followup.send(embed=embed)

    @project_group.command(name="finish", description="Conclude project sprint, lock display channels, and generate final retrospective report")
    @app_commands.default_permissions(manage_channels=True)
    async def project_finish(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be run inside a server.", ephemeral=True)
            return

        try:
            summary_dto = await self.project_service.archive_project(
                guild_id=str(guild.id),
                archived_by_user_id=interaction.user.display_name
            )

            # Update channel topics to [ARCHIVED]
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            for name in ["tasks", "deadlines", "submissions"]:
                ch = discord.utils.get(guild.text_channels, name=name)
                if ch and guild.me.guild_permissions.manage_channels:
                    try:
                        await ch.edit(topic=f"[ARCHIVED] - Completed on {date_str}. Preserved in read-only mode.")
                    except Exception:
                        pass

            retrospective_embed = build_project_archive_embed(summary_dto, guild.name)

            # Post final retrospective in #submissions
            sub_ch = discord.utils.get(guild.text_channels, name="submissions")
            if sub_ch:
                await sub_ch.send(content="🎓 **FINAL PROJECT RETROSPECTIVE:**", embed=retrospective_embed)

            await interaction.followup.send(
                content=f"🎉 **Project officially concluded and archived!** Retrospective report posted to {sub_ch.mention if sub_ch else 'channels'}.",
                embed=retrospective_embed
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

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
            name="3. 📊 Anti-Free-Riding Reports & Submissions",
            value=(
                "`/submit file:<attachment> [notes:<text>]` — Upload deliverable with hash verification\n"
                "`/report` — View team contribution ranking\n"
                "`/report <@member>` — View individual completion rate and message volume"
            ),
            inline=False
        )
        embed.add_field(
            name="4. 🚀 Project Lifecycle",
            value=(
                "`/project status` — View overall project completion and upcoming milestones\n"
                "`/project finish` — Archive project sprint and generate final retrospective report"
            ),
            inline=False
        )
        embed.set_footer(text="Automated alerts: T-24h & T-1h for tasks; T-72h, T-24h & T-6h for milestones.")
        await interaction.response.send_message(embed=embed)
