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

    async def _ensure_channels_and_roles(self, guild: discord.Guild) -> List[discord.TextChannel]:
        """Creates or updates all project and Squid Game channels and roles with appropriate protections."""
        # 1. Provision Player and Spectator roles
        if guild.me.guild_permissions.manage_roles:
            if not discord.utils.get(guild.roles, name="Player"):
                try:
                    await guild.create_role(
                        name="Player",
                        color=discord.Color.from_rgb(3, 122, 118),
                        mentionable=True,
                        reason="Squid Game accountability role"
                    )
                except Exception as e:
                    logger.warning("Could not auto-create Player role in guild %s: %s", guild.id, e)

            if not discord.utils.get(guild.roles, name="Spectator"):
                try:
                    await guild.create_role(
                        name="Spectator",
                        color=discord.Color.from_rgb(120, 120, 120),
                        mentionable=True,
                        reason="Squid Game spectator role"
                    )
                except Exception as e:
                    logger.warning("Could not auto-create Spectator role in guild %s: %s", guild.id, e)

        # 2. Provision Channels
        channel_configs = [
            ("tasks", "📋 Group task ledger. Read-only display. Use /task to interact.", False),
            ("deadlines", "🎯 Major project milestones and live countdowns. Read-only display. Use /deadline to interact.", False),
            ("submissions", "📥 Verified deliverable submission vault. Read-only display. Use /submit to upload.", False),
            ("wall-of-shame", "🚨 Public accountability ledger. Overdue tasks and broken streaks are recorded here.", False),
            ("game-hub", "🎮 Squid Game Arena & Minigame Hub. Type /squid join to get your 3-digit player number.", True),
            ("spectators", "💀 Observation deck for eliminated players.", False)
        ]

        created_or_found = []
        for name, topic, allow_chat in channel_configs:
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True,
                    read_message_history=True,
                    send_messages=allow_chat,
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

            ch = discord.utils.get(guild.text_channels, name=name)
            is_new = False
            if not ch and guild.me.guild_permissions.manage_channels:
                try:
                    ch = await guild.create_text_channel(name=name, topic=topic, overwrites=overwrites)
                    is_new = True
                except Exception as e:
                    logger.warning("Could not auto-create #%s in guild %s: %s", name, guild.name, e)
            elif ch and guild.me.guild_permissions.manage_channels:
                try:
                    await ch.edit(topic=topic, overwrites=overwrites)
                except Exception as e:
                    logger.warning("Could not enforce permissions on #%s: %s", name, e)

            if ch:
                created_or_found.append(ch)
                if is_new and name == "game-hub":
                    welcome_embed = discord.Embed(
                        title="○ △ □ SQUID GAME ARENA • INITIALIZED",
                        description=(
                            "Welcome to the accountability arena.\n\n"
                            "**How to play:**\n"
                            "• Type `/squid join` to enroll and receive your 3-digit tag (`001`–`456`).\n"
                            "• Type `/squid status` to view the live piggy bank prize pool and survivor count.\n"
                            "• Type `/move` to take steps during active Red Light Green Light rounds.\n"
                            "• **Warning:** Missing your project deadlines will result in immediate termination."
                        ),
                        color=discord.Color.from_rgb(255, 0, 144)
                    )
                    welcome_embed.set_footer(text="Obey all directives from the Masked Guards.")
                    try:
                        await ch.send(embed=welcome_embed)
                    except Exception:
                        pass

        return created_or_found

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Auto-provisions group work channels and roles on joining a new server."""
        logger.info("Bot joined guild %s (%s). Provisioning channels and roles...", guild.name, guild.id)
        await self._ensure_channels_and_roles(guild)

    @app_commands.command(
        name="setup",
        description="Provision all project channels, Squid Game arena, and roles at once"
    )
    @app_commands.default_permissions(manage_channels=True)
    async def setup_channels(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be run in a server.", ephemeral=True)
            return

        channels = await self._ensure_channels_and_roles(guild)
        ch_list = ", ".join(c.mention for c in channels) if channels else "None"

        embed = discord.Embed(
            title="🛠️ Server Environment Fully Configured",
            description=f"All channels and roles have been provisioned:\n\n{ch_list}",
            color=COLOR_SUCCESS
        )
        embed.add_field(
            name="🔒 Accountability Channels (Read-Only)",
            value="• `#tasks` — Live task ledger\n• `#deadlines` — Pinned countdowns\n• `#submissions` — Verified file vault\n• `#wall-of-shame` — Overdue warnings",
            inline=True
        )
        embed.add_field(
            name="🎮 Squid Game Arena (Interactive)",
            value="• `#game-hub` — Lobby, announcements, minigames & elimination feed\n• `#spectators` — Fallen players observation deck",
            inline=True
        )
        embed.add_field(
            name="Quick Start Actions",
            value=(
                "1. Head over to <#game-hub> and type `/squid join` to claim your player number.\n"
                "2. Assign group tasks with `/task add`.\n"
                "3. View team rankings and on-time streaks with `/report`."
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
            for name in ["tasks", "deadlines", "submissions", "wall-of-shame"]:
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
            name="1. 📋 Task Ledger & Interactive Buttons",
            value=(
                "`/task add <desc> <@member> <YYYY-MM-DD>` — Assign deliverable task\n"
                "`/task complete <TASK-ID>` — Mark completed\n"
                "`/task list` — View pending tasks\n"
                "• **Task Cards** include 🔔 **Nudge**, 🔄 **In Progress**, and ✅ **Complete** buttons!"
            ),
            inline=False
        )
        embed.add_field(
            name="2. 🚨 Wall of Shame & On-Time Streaks",
            value=(
                "• Missing deadlines automatically posts overdue alerts to `#wall-of-shame`.\n"
                "• Overdue tasks break your consecutive on-time streak (`🔥 0`)!\n"
                "• Complete on time to rank up: Comrade → Sergeant → Colonel → Marshal → General Secretary."
            ),
            inline=False
        )
        embed.add_field(
            name="3. 🎯 Deadlines & Alerts",
            value=(
                "`/deadline add <name> <YYYY-MM-DD HH:MM>` — Pin live countdown in `#deadlines`\n"
                "`/deadline list` — View active milestones\n"
                "`/deadline complete <DL-ID>` — Archive finished deadline"
            ),
            inline=False
        )
        embed.add_field(
            name="4. 📊 Anti-Free-Riding Reports & Submissions",
            value=(
                "`/submit file:<attachment> [notes:<text>]` — Upload deliverable with hash verification\n"
                "`/report` — View team ranking with on-time streaks and military ranks\n"
                "`/report <@member>` — View individual scorecard and deliverable history"
            ),
            inline=False
        )
        embed.add_field(
            name="5. 🚀 Project Lifecycle",
            value=(
                "`/project status` — View overall project completion and upcoming milestones\n"
                "`/project finish` — Archive project sprint and generate final retrospective report"
            ),
            inline=False
        )
        embed.set_footer(text="Automated alerts: T-24h & T-1h for tasks; T-72h, T-24h & T-6h for milestones.")
        await interaction.response.send_message(embed=embed)
