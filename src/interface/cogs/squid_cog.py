"""
Squid Game Discord slash commands Cog.

What it does:
- Exposes /squid commands (join, status, announce, eliminate, redlight) and /move.
- Delivers masked guard and doll audio clips via AudioDeliverer.

What it does NOT do:
- Does NOT implement database persistence or direct subprocesses.
"""

import logging
import asyncio
import random
from typing import Optional, Literal
import discord
from discord import app_commands
from discord.ext import commands

from src.application.services.squid_service import SquidService
from src.application.dtos.squid_dtos import EnrollPlayerDTO, RedLightMoveDTO
from src.domain.interfaces.audio_deliverer import AudioDeliverer
from src.domain.entities.guard_voice import GuardVoiceLines, GUARD_PROFILE, DOLL_PROFILE
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer
from src.interface.squid_formatters import (
    build_squid_enrollment_embed,
    build_squid_elimination_embed,
    build_squid_status_embed,
    build_red_light_embed
)
from src.domain.errors import AppError
from src.interface.red_light_runner import RedLightRunner
from src.interface.channel_router import ChannelRouter
from src.interface.views.move_view import MoveView

logger = logging.getLogger("interface.cogs.squid")

class SquidCog(commands.GroupCog, group_name="squid"):
    """Squid Game accountability theme and minigames engine."""

    def __init__(
        self,
        bot: commands.Bot,
        squid_service: SquidService,
        audio_deliverer: AudioDeliverer,
        synthesizer: Optional[SpeechSynthesizer] = None,
        channel_router: Optional[ChannelRouter] = None
    ):
        self.bot = bot
        self.squid_service = squid_service
        self.audio_deliverer = audio_deliverer
        self.synthesizer = synthesizer
        self.channel_router = channel_router
        self.runner = RedLightRunner(
            bot, squid_service, audio_deliverer, synthesizer, channel_router=channel_router
        )
        self._running_tasks: dict = {}
        super().__init__()

    async def cog_load(self):
        """Registers persistent views and resets stale sessions across restarts."""
        self.bot.add_view(MoveView(self.squid_service, self.channel_router))
        self.squid_service.reset_all_games()

    async def _ensure_game_hub(self, interaction: discord.Interaction) -> bool:
        """Enforces that gameplay commands execute only inside #game-hub."""
        if not interaction.guild or not self.channel_router:
            return True
        hub = await self.channel_router.resolve(interaction.guild, "game-hub")
        if hub and interaction.channel_id != hub.id:
            await interaction.followup.send(
                f"⚠️ **Wrong Arena:** Squid Game commands can only be played in {hub.mention}!",
                ephemeral=True
            )
            return False
        return True

    def cog_unload(self):
        for task in self._running_tasks.values():
            task.cancel()

    async def _swap_to_spectator(self, guild: discord.Guild, user_id: str) -> None:
        """Atomically removes Player role and grants Spectator role."""
        try:
            member = guild.get_member(int(user_id))
            if not member:
                return
            p_role = discord.utils.get(guild.roles, name="Player")
            s_role = discord.utils.get(guild.roles, name="Spectator")
            if p_role and p_role in member.roles:
                await member.remove_roles(p_role, reason="Eliminated in Squid Game")
            if s_role and s_role not in member.roles:
                await member.add_roles(s_role, reason="Moved to Spectator deck")
        except Exception as e:
            logger.warning("Could not swap role to Spectator for user %s: %s", user_id, e)

    async def _revive_roles(self, guild: discord.Guild) -> None:
        """Restores Player role and removes Spectator role for all enrolled contestants."""
        p_role = discord.utils.get(guild.roles, name="Player")
        s_role = discord.utils.get(guild.roles, name="Spectator")
        if not p_role:
            return
        players = await self.squid_service.squid_repo.list_players(str(guild.id))
        for p in players:
            try:
                member = guild.get_member(int(p.user_id))
                if member:
                    if s_role and s_role in member.roles:
                        await member.remove_roles(s_role, reason="Squid Game revive")
                    if p_role and p_role not in member.roles:
                        await member.add_roles(p_role, reason="Squid Game revive")
            except Exception:
                pass

    @app_commands.command(name="join", description="Enroll in the Squid Game accountability roster and receive a player number")
    async def join(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        if not await self._ensure_game_hub(interaction):
            return

        guild_id = str(interaction.guild_id)
        if self.squid_service.get_active_game(guild_id):
            await interaction.followup.send(
                "⛔ **The arena doors are locked!** A match is currently in progress. You must wait for the current session to conclude before joining.",
                ephemeral=True
            )
            return

        dto = EnrollPlayerDTO(guild_id=guild_id, user_id=str(interaction.user.id))
        try:
            result = await self.squid_service.enroll_player(dto)
            if interaction.guild and isinstance(interaction.user, discord.Member):
                p_role = discord.utils.get(interaction.guild.roles, name="Player")
                s_role = discord.utils.get(interaction.guild.roles, name="Spectator")
                if s_role and s_role in interaction.user.roles:
                    await interaction.user.remove_roles(s_role)
                if p_role and p_role not in interaction.user.roles:
                    await interaction.user.add_roles(p_role)

            avatar_url = interaction.user.display_avatar.url if interaction.user else None
            embed = build_squid_enrollment_embed(result, avatar_url=avatar_url)
            await interaction.followup.send(embed=embed)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @app_commands.command(name="status", description="View current prize pot piggy bank and survivor count")
    async def status(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        try:
            status_dto = await self.squid_service.get_status(str(interaction.guild_id))
            embed = build_squid_status_embed(status_dto)
            await interaction.followup.send(embed=embed)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @app_commands.command(name="announce", description="Broadcast an official Masked Guard announcement with audio")
    @app_commands.describe(text="The official directive or warning to broadcast")
    async def announce(self, interaction: discord.Interaction, text: str):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        audio_bytes = None
        if self.synthesizer:
            try:
                audio_bytes = await self.synthesizer.synthesize(text, GUARD_PROFILE)
            except Exception as e:
                logger.error("Failed to synthesize guard announcement: %s", e)

        embed = discord.Embed(
            title="○ △ □ OFFICIAL GUARD DIRECTIVE",
            description=f"**{text}**",
            color=discord.Color.from_rgb(255, 0, 144)
        )
        embed.set_footer(text="Masked Guard Broadcast • Obey all commands")

        if audio_bytes:
            await self.audio_deliverer.deliver(
                target=interaction,
                audio_bytes=audio_bytes,
                filename="guard_announcement.wav",
                embed=embed
            )
        else:
            await interaction.followup.send(embed=embed)

    @app_commands.command(name="eliminate", description="Front Man command: manually eliminate a player with full guard audio")
    @app_commands.describe(member="Member to eliminate", reason="Reason for termination")
    async def eliminate(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        try:
            result = await self.squid_service.eliminate_player(
                guild_id=str(interaction.guild_id),
                user_id=str(member.id),
                reason=reason,
                synthesize_audio=True
            )
            if interaction.guild:
                await self._swap_to_spectator(interaction.guild, str(member.id))

            avatar_url = member.display_avatar.url if member else None
            embed = build_squid_elimination_embed(result, avatar_url=avatar_url)
            if result.audio_bytes:
                await self.audio_deliverer.deliver(
                    target=interaction,
                    audio_bytes=result.audio_bytes,
                    filename=f"elimination_{result.player_number}.wav",
                    embed=embed
                )
            else:
                await interaction.followup.send(embed=embed)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @app_commands.command(name="reset", description="Front Man command: revive all contestants and reset prize pot")
    async def reset(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        guild_id = str(interaction.guild_id)
        revived = await self.squid_service.revive_all_players(guild_id)
        await self.squid_service.reset_season(guild_id)
        if interaction.guild:
            await self._revive_roles(interaction.guild)

        embed = discord.Embed(
            title="○ △ □ ARENA RESET • NEW CYCLE INITIATED",
            description=f"🔄 **All {revived} contestants have been revived and granted Player status.**\n💰 Piggy bank prize pool reset to `₩ 0`.",
            color=discord.Color.from_rgb(255, 0, 144)
        )
        embed.set_footer(text="A fresh game can now be started with /squid redlight action:start")
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="redlight", description="Run or stop the automated Red Light Green Light game loop")
    @app_commands.describe(action="start (automated loop), stop, or manual phase trigger")
    async def redlight(self, interaction: discord.Interaction, action: Literal["start", "stop", "green", "red"]):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        if not await self._ensure_game_hub(interaction):
            return

        guild_id = str(interaction.guild_id)
        if action == "stop":
            running = self._running_tasks.pop(guild_id, None)
            if running:
                running.cancel()
            self.squid_service.end_red_light_game(guild_id)
            await interaction.followup.send("🛑 **Red Light Green Light game terminated by the Front Man.**")
            return

        if action == "green":
            self.squid_service.set_light(guild_id, "GREEN")
            await interaction.followup.send("🟢 **Light manually set to GREEN.**")
            return

        if action == "red":
            self.squid_service.set_light(guild_id, "RED")
            await interaction.followup.send("🔴 **Light manually set to RED.**")
            return

        if guild_id in self._running_tasks and not self._running_tasks[guild_id].done():
            await interaction.followup.send("⚠️ **A game is already in progress in this server!** Use `/squid redlight action:stop` to abort.", ephemeral=True)
            return

        # Check enrolled contestants who are alive and ready to play
        alive_players = await self.squid_service.squid_repo.list_players(guild_id, alive_only=True)
        if not alive_players:
            await interaction.followup.send(
                "⚠️ **Cannot start Squid Game:** At least 1 player must join first! Active contestants must run `/squid join` to participate.",
                ephemeral=True
            )
            return

        await interaction.followup.send(
            f"🎮 **{len(alive_players)} contestant(s) assembled on the track! Initiating Red Light Green Light session...**"
        )
        task = self.bot.loop.create_task(
            self.runner.run(interaction.channel, guild_id, on_cleanup=lambda gid: self._running_tasks.pop(gid, None))
        )
        self._running_tasks[guild_id] = task

async def setup(bot: commands.Bot):
    # Cogs mounted directly in bot.py
    pass
