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

logger = logging.getLogger("interface.cogs.squid")

class SquidCog(commands.GroupCog, group_name="squid"):
    """Squid Game accountability theme and minigames engine."""

    def __init__(
        self,
        bot: commands.Bot,
        squid_service: SquidService,
        audio_deliverer: AudioDeliverer,
        synthesizer: Optional[SpeechSynthesizer] = None
    ):
        self.bot = bot
        self.squid_service = squid_service
        self.audio_deliverer = audio_deliverer
        self.synthesizer = synthesizer
        self._running_tasks: dict = {}
        super().__init__()

    def cog_unload(self):
        for task in self._running_tasks.values():
            task.cancel()

    @app_commands.command(name="join", description="Enroll in the Squid Game accountability roster and receive a player number")
    async def join(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        dto = EnrollPlayerDTO(guild_id=str(interaction.guild_id), user_id=str(interaction.user.id))
        try:
            result = await self.squid_service.enroll_player(dto)
            embed = build_squid_enrollment_embed(result)
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
            embed = build_squid_elimination_embed(result)
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

    @app_commands.command(name="redlight", description="Run or stop the automated Red Light Green Light game loop")
    @app_commands.describe(action="start (automated loop), stop, or manual phase trigger")
    async def redlight(self, interaction: discord.Interaction, action: Literal["start", "stop", "green", "red"]):
        try:
            await interaction.response.defer()
        except discord.NotFound:
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

        await interaction.followup.send("🎮 **Initiating Red Light Green Light automated session...** Listen closely to the audio cues!")
        task = self.bot.loop.create_task(self._run_automated_session(interaction.channel, guild_id))
        self._running_tasks[guild_id] = task

    async def _run_automated_session(self, channel, guild_id: str):
        """Runs the automated Red Light Green Light background cycle."""
        try:
            self.squid_service.start_red_light_game(guild_id, target=100)
            if self.synthesizer:
                script = GuardVoiceLines.game_announcement("Red Light Green Light")
                intro_audio = await self.synthesizer.synthesize(script, GUARD_PROFILE)
                await self.audio_deliverer.deliver(channel, intro_audio, "intro.wav", content="🚨 **Game beginning in 5 seconds!**")
            await asyncio.sleep(5.0)

            for round_num in range(1, 6):
                game = self.squid_service.get_active_game(guild_id)
                if not game:
                    break

                # 1. GREEN LIGHT
                self.squid_service.set_light(guild_id, "GREEN")
                green_audio = None
                if self.synthesizer:
                    try:
                        green_audio = await self.synthesizer.synthesize(GuardVoiceLines.green_light_korean(), DOLL_PROFILE)
                    except Exception:
                        green_audio = await self.synthesizer.synthesize(GuardVoiceLines.green_light_english(), GUARD_PROFILE)
                embed = build_red_light_embed("GREEN", game.get("target", 100), game.get("progress", {}))
                if green_audio:
                    await self.audio_deliverer.deliver(channel, green_audio, "doll_green.wav", embed=embed)
                else:
                    await channel.send(embed=embed)
                await asyncio.sleep(random.uniform(4.5, 7.0))

                # 2. RED LIGHT
                self.squid_service.set_light(guild_id, "RED")
                red_audio = await self.synthesizer.synthesize(GuardVoiceLines.red_light(), GUARD_PROFILE) if self.synthesizer else None
                embed = build_red_light_embed("RED", game.get("target", 100), game.get("progress", {}))
                if red_audio:
                    await self.audio_deliverer.deliver(channel, red_audio, "doll_red.wav", embed=embed)
                else:
                    await channel.send(embed=embed)
                await asyncio.sleep(random.uniform(3.5, 5.0))

            self.squid_service.end_red_light_game(guild_id)
            await channel.send("🏁 **Red Light Green Light session completed!** Check `/squid status` for survivors and updated prize pool.")
        except asyncio.CancelledError:
            logger.info("Red light automated session cancelled for guild %s", guild_id)
        except Exception as e:
            logger.error("Error in automated red light session: %s", e, exc_info=True)
            self.squid_service.end_red_light_game(guild_id)

class MoveCommandCog(commands.Cog):
    """Top-level /move command for Red Light Green Light gameplay."""

    def __init__(
        self,
        bot: commands.Bot,
        squid_service: SquidService,
        audio_deliverer: AudioDeliverer
    ):
        self.bot = bot
        self.squid_service = squid_service
        self.audio_deliverer = audio_deliverer

    @app_commands.command(name="move", description="Take steps in Red Light Green Light (Safe only during Green Light!)")
    async def move(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
        except discord.NotFound:
            return

        dto = RedLightMoveDTO(guild_id=str(interaction.guild_id), user_id=str(interaction.user.id))
        try:
            res = await self.squid_service.process_move(dto)
            if not res.survived:
                embed = discord.Embed(
                    title="💀 SQUID GAME • ELIMINATION CONFIRMED",
                    description=f"🚨 **`{res.player_number}` (<@{res.user_id}>) MOVED DURING RED LIGHT!**\nPlayer has been terminated.",
                    color=discord.Color.from_rgb(255, 0, 144)
                )
                if res.audio_bytes:
                    await self.audio_deliverer.deliver(interaction, res.audio_bytes, "eliminated.wav", embed=embed)
                else:
                    await interaction.followup.send(embed=embed)
            else:
                badge = "🏁" if res.is_finished else "🏃"
                await interaction.followup.send(f"{badge} **Player {res.player_number}**: {res.status_message}")
        except AppError as e:
            await interaction.followup.send(f"⚠️ {e.message}", ephemeral=True)

async def setup(bot: commands.Bot):
    # Cogs mounted directly in bot.py
    pass
