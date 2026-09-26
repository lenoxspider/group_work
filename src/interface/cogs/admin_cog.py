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
from typing import List, Optional, Literal, Tuple
import discord
from discord import app_commands
from discord.ext import commands

from src.application.services.project_service import ProjectService
from src.interface.channel_router import ChannelRouter
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

    CATEGORY_NAME = "TOVARISHCH"

    def __init__(
        self,
        bot: commands.Bot,
        project_service: ProjectService,
        channel_router: ChannelRouter
    ):
        self.bot = bot
        self.project_service = project_service
        self.channel_router = channel_router

    project_group = app_commands.Group(name="project", description="Group project and sprint lifecycle commands")

    async def _ensure_channels_and_roles(
        self,
        guild: discord.Guild,
        repair: bool = False
    ) -> Tuple[List[discord.TextChannel], Optional[str]]:
        """Creates or repairs all project channels, TOVARISHCH category, and role permissions."""
        hierarchy_warning = None

        # 1. Provision Player and Spectator roles
        player_role = discord.utils.get(guild.roles, name="Player")
        spectator_role = discord.utils.get(guild.roles, name="Spectator")

        if guild.me.guild_permissions.manage_roles:
            if not player_role:
                try:
                    player_role = await guild.create_role(
                        name="Player",
                        color=discord.Color.from_rgb(3, 122, 118),
                        mentionable=True,
                        reason="Squid Game accountability contestant role"
                    )
                except Exception as e:
                    logger.warning("Could not auto-create Player role in guild %s: %s", guild.id, e)

            if not spectator_role:
                try:
                    spectator_role = await guild.create_role(
                        name="Spectator",
                        color=discord.Color.from_rgb(120, 120, 120),
                        mentionable=True,
                        reason="Squid Game observation role"
                    )
                except Exception as e:
                    logger.warning("Could not auto-create Spectator role in guild %s: %s", guild.id, e)

        # Hierarchy check
        if player_role and guild.me.top_role.position <= player_role.position:
            hierarchy_warning = (
                f"⚠️ **Role Hierarchy Warning**: Bot's top role (`{guild.me.top_role.name}`) is below "
                f"or equal to the `Player` role! Please drag the bot's role higher in Server Settings → Roles."
            )

        # 2. Provision or resolve TOVARISHCH Category
        category = discord.utils.get(guild.categories, name=self.CATEGORY_NAME)
        if not category and guild.me.guild_permissions.manage_channels:
            try:
                category = await guild.create_category(name=self.CATEGORY_NAME)
            except Exception as e:
                logger.warning("Could not create %s category in guild %s: %s", self.CATEGORY_NAME, guild.id, e)

        # 3. Channel configuration matrix
        read_only_everyone = discord.PermissionOverwrite(
            view_channel=True,
            read_message_history=True,
            send_messages=False,
            send_messages_in_threads=False,
            create_public_threads=False,
            create_private_threads=False,
            add_reactions=False,
            manage_webhooks=False,
            use_application_commands=False
        )

        bot_full = discord.PermissionOverwrite(
            view_channel=True,
            send_messages=True,
            manage_messages=True,
            embed_links=True,
            attach_files=True,
            read_message_history=True,
            manage_webhooks=True
        )

        channel_configs = [
            ("tasks", "📋 Group task ledger. Read-only display. Use /task to interact.", {
                guild.default_role: read_only_everyone,
                guild.me: bot_full
            }),
            ("deadlines", "🎯 Major project milestones and live countdowns. Read-only display.", {
                guild.default_role: read_only_everyone,
                guild.me: bot_full
            }),
            ("submissions", "📥 Verified deliverable submission vault. Read-only audit receipts.", {
                guild.default_role: read_only_everyone,
                guild.me: bot_full
            }),
            ("wall-of-shame", "🚨 Public accountability ledger. Overdue tasks recorded here.", {
                guild.default_role: read_only_everyone,
                guild.me: bot_full
            }),
            ("game-hub", "🎮 Squid Game Arena. Only active Players can execute commands.", {
                guild.default_role: discord.PermissionOverwrite(
                    view_channel=True, read_message_history=True, send_messages=False, use_application_commands=True
                ),
                guild.me: bot_full,
                **(
                    {player_role: discord.PermissionOverwrite(
                        view_channel=True, read_message_history=True, send_messages=True, use_application_commands=True, add_reactions=True
                    )} if player_role else {}
                ),
                **(
                    {spectator_role: discord.PermissionOverwrite(
                        view_channel=True, read_message_history=True, send_messages=False, use_application_commands=False
                    )} if spectator_role else {}
                )
            }),
            ("spectators", "💀 Observation deck for eliminated contestants.", {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: bot_full,
                **(
                    {spectator_role: discord.PermissionOverwrite(
                        view_channel=True, read_message_history=True, send_messages=True
                    )} if spectator_role else {}
                )
            }),
            ("bot-log", "🛡️ Bot admin and security audit log. Private to staff and bot.", {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                guild.me: bot_full
            })
        ]

        created_or_found = []
        bindings = {}
        for name, topic, overwrites in channel_configs:
            ch = discord.utils.get(guild.text_channels, name=name)
            is_new = False
            if not ch and guild.me.guild_permissions.manage_channels:
                try:
                    ch = await guild.create_text_channel(
                        name=name,
                        topic=topic,
                        category=category,
                        overwrites=overwrites
                    )
                    is_new = True
                except Exception as e:
                    logger.warning("Could not auto-create #%s in guild %s: %s", name, guild.name, e)
            elif ch and repair and guild.me.guild_permissions.manage_channels:
                try:
                    await ch.edit(topic=topic, category=category, overwrites=overwrites)
                except Exception as e:
                    logger.warning("Could not repair overwrites on #%s: %s", name, e)

            if ch:
                created_or_found.append(ch)
                bindings[name] = str(ch.id)
                if is_new and name == "game-hub":
                    welcome_embed = discord.Embed(
                        title="○ △ □ SQUID GAME ARENA • INITIALIZED",
                        description=(
                            "Welcome to the accountability arena.\n\n"
                            "**How to play:**\n"
                            "• Type `/squid join` to claim your player tag (`001`–`456`) and gain arena access.\n"
                            "• Eliminated players are moved to the private <#spectators> lounge.\n"
                            "• Obey all directives from the Masked Guards."
                        ),
                        color=discord.Color.from_rgb(255, 0, 144)
                    )
                    try:
                        await ch.send(embed=welcome_embed)
                    except Exception:
                        pass

        # 4. Persist bindings in SQLite
        await self.channel_router.bind_all(str(guild.id), bindings)
        return created_or_found, hierarchy_warning

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        """Auto-provisions group work channels and roles on joining a new server."""
        logger.info("Bot joined guild %s (%s). Provisioning channels and roles...", guild.name, guild.id)
        await self._ensure_channels_and_roles(guild)

    @app_commands.command(
        name="setup",
        description="Provision or repair all project channels, TOVARISHCH category, and role permissions"
    )
    @app_commands.describe(action="setup (create missing) or repair (re-enforce all permission locks and bindings)")
    @app_commands.default_permissions(manage_channels=True)
    async def setup_channels(
        self,
        interaction: discord.Interaction,
        action: Literal["setup", "repair"] = "setup"
    ):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be run in a server.", ephemeral=True)
            return

        is_repair = (action == "repair")
        channels, hierarchy_warning = await self._ensure_channels_and_roles(guild, repair=is_repair)
        ch_list = ", ".join(c.mention for c in channels) if channels else "None"

        embed = discord.Embed(
            title="🛠️ Server Environment Fully Configured" if not is_repair else "🔧 Server Permissions Repaired",
            description=f"All channels under **TOVARISHCH** and roles are synchronized:\n\n{ch_list}",
            color=COLOR_SUCCESS
        )
        if hierarchy_warning:
            embed.add_field(name="⚠️ Attention Needed", value=hierarchy_warning, inline=False)

        embed.add_field(
            name="🔒 Immutable Ledgers",
            value="• `#tasks`\n• `#deadlines`\n• `#submissions`\n• `#wall-of-shame`",
            inline=True
        )
        embed.add_field(
            name="🎮 Squid Game Arena",
            value="• `#game-hub` (Player role only)\n• `#spectators` (Private eliminated deck)",
            inline=True
        )
        await interaction.followup.send(embed=embed)

    @project_group.command(name="status", description="View overall project progress, task health, and milestone countdown")
    async def project_status(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return
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
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return
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
