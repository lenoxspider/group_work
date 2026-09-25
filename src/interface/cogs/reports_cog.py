"""
Contribution report Discord Cog interface.

What it does:
- Exposes /report slash command for individual scorecards and team standings.
- Serializes report DTOs into visual embeds with progress bars.

What it does NOT do:
- Does NOT calculate contribution weights or query database directly.
"""

import io
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.application.services.activity_service import ActivityService
from src.application.services.voice_service import VoiceService
from src.application.dtos.voice_dtos import SynthesizeRequestDTO
from src.interface.discord_formatters import (
    build_member_report_embed,
    build_guild_report_embed
)

class ReportsCog(commands.Cog, name="Contribution Reports"):
    """Interface adapter for anti-free-riding contribution reports."""

    def __init__(
        self,
        bot: commands.Bot,
        activity_service: ActivityService,
        voice_service: Optional[VoiceService] = None
    ):
        self.bot = bot
        self.service = activity_service
        self.voice_service = voice_service

    @app_commands.command(
        name="report",
        description="View team contribution metrics, tasks completed, messages, and file submissions"
    )
    @app_commands.describe(
        member="Optional: Select a specific team member to view their individual stats",
        voice="Optional: Read the summary aloud with audio voice briefing"
    )
    async def report(
        self,
        interaction: discord.Interaction,
        member: Optional[discord.Member] = None,
        voice: bool = False
    ):
        await interaction.response.defer()
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command must be executed within a server.", ephemeral=True)
            return

        guild_id = str(guild.id)
        voice_file = None

        if member:
            dto = await self.service.get_member_report(guild_id, str(member.id))
            embed = build_member_report_embed(dto, member)
            if voice and self.voice_service:
                script = (
                    f"Member report for {member.display_name}. Rank: {dto.rank_title}. "
                    f"Current streak: {dto.current_streak} tasks on time. "
                    f"Completed {dto.tasks_completed} tasks, with an on-time rate of {dto.on_time_rate_pct} percent."
                )
                try:
                    clip = await self.voice_service.synthesize(
                        SynthesizeRequestDTO(text=script, user_id=str(member.id), tone="serious")
                    )
                    voice_file = discord.File(io.BytesIO(clip.audio_bytes), filename="member_report.wav")
                except Exception:
                    pass
            await interaction.followup.send(embed=embed, file=voice_file)
            return

        guild_dto = await self.service.get_guild_report(guild_id)
        embed = build_guild_report_embed(guild_dto, guild)

        if voice and self.voice_service:
            leader_name = "Team"
            leader_score = 0.0
            if guild_dto.members:
                top = guild_dto.members[0]
                top_m = guild.get_member(int(top.user_id))
                leader_name = top_m.display_name if top_m else f"Member {top.user_id}"
                leader_score = top.contribution_score

            script = self.voice_service.generate_report_script(
                leader_name=leader_name,
                leader_score=leader_score,
                overdue_count=guild_dto.overdue_tasks_count,
                total_tasks=guild_dto.total_tasks,
                completed_tasks=guild_dto.total_tasks_completed
            )
            try:
                clip = await self.voice_service.synthesize(SynthesizeRequestDTO(text=script, tone="serious"))
                voice_file = discord.File(io.BytesIO(clip.audio_bytes), filename="guild_report.wav")
            except Exception:
                pass

        await interaction.followup.send(embed=embed, file=voice_file)
