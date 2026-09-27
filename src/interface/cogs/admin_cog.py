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

    def __init__(
        self,
        bot: commands.Bot,
        project_service: ProjectService
    ):
        self.bot = bot
        self.project_service = project_service

    project_group = app_commands.Group(name="project", description="Group project and sprint lifecycle commands")

    async def _ensure_channels_and_roles(
        self,
        guild: discord.Guild,
        repair: bool = False
    ) -> Tuple[List[discord.TextChannel], Optional[str]]:
        """Creates or repairs squid roles, then provisions every plugin's declared channels."""
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

            if not discord.utils.get(guild.roles, name="Catizen"):
                try:
                    await guild.create_role(
                        name="Catizen",
                        color=discord.Color.from_rgb(200, 160, 100),
                        mentionable=False,
                        reason="Un-signed community recruit (pre-citizenship)"
                    )
                except Exception as e:
                    logger.warning("Could not auto-create Catizen role in guild %s: %s", guild.id, e)

        # Hierarchy check
        if player_role and guild.me.top_role.position <= player_role.position:
            hierarchy_warning = (
                f"⚠️ **Role Hierarchy Warning**: Bot's top role (`{guild.me.top_role.name}`) is below "
                f"or equal to the `Player` role! Please drag the bot's role higher in Server Settings → Roles."
            )

        # Provision every plugin's declared channels via the shared ChannelManager
        created_or_found, _ = await self.bot.channel_manager.provision_all(guild, repair=repair)
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

    @app_commands.command(name="guide", description="View the full command reference for the server")
    async def guide(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📖 Server Guide",
            description="A self-governing server: work pays spi, the bank moves it, the radio plays it, and the society rules it.",
            color=COLOR_PRIMARY
        )
        for plugin in self.bot.plugins.values():
            if not plugin.guide:
                continue
            lines = [f"`{cmd}` - {desc}" for cmd, desc in plugin.guide]
            value = plugin.summary + "\n" + "\n".join(lines)
            embed.add_field(name=plugin.title or plugin.name, value=value, inline=False)
        embed.set_footer(text="Type / to browse commands. Run /setup to provision channels and roles.")
        await interaction.response.send_message(embed=embed)
