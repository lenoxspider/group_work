"""
Task ledger Discord Cog interface.

What it does:
- Exposes /task slash commands (add, complete, list).
- Dispatches background T-24h and T-1h DM reminders.
- Formats interaction responses using discord_formatters.

What it does NOT do:
- Does NOT contain task business logic or database queries directly.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.application.dtos.task_dtos import CreateTaskDTO
from src.application.dtos.extension_dtos import CreateExtensionDTO
from src.application.dtos.voice_dtos import SynthesizeRequestDTO
from src.application.services.task_service import TaskService
from src.application.services.extension_service import ExtensionService
from src.application.services.preference_service import PreferenceService
from src.application.services.voice_service import VoiceService
from src.domain.errors import AppError
from src.interface.cogs.task_buttons import TaskActionView
from src.interface.cogs.extension_buttons import ExtensionVoteView
from src.interface.discord_formatters import (
    build_task_embed,
    build_wall_of_shame_embed,
    build_extension_vote_embed,
    format_discord_timestamps,
    COLOR_PRIMARY,
    COLOR_WARNING,
    COLOR_DANGER
)

logger = logging.getLogger("interface.cogs.tasks")

class TasksCog(commands.Cog, name="Task Ledger"):
    """Interface adapter for Task management commands, extension voting, and escalating reminders."""

    def __init__(
        self,
        bot: commands.Bot,
        task_service: TaskService,
        extension_service: ExtensionService,
        preference_service: Optional[PreferenceService] = None,
        voice_service: Optional[VoiceService] = None
    ):
        self.bot = bot
        self.service = task_service
        self.extension_service = extension_service
        self.preference_service = preference_service
        self.voice_service = voice_service
        self.bot.add_view(TaskActionView(task_service))
        self.bot.add_view(ExtensionVoteView(extension_service))

    async def _try_generate_voice_file(self, script: str, user_id: str, tone: str = "drill_sergeant") -> Optional[discord.File]:
        if not self.voice_service or not script:
            return None
        try:
            clip = await self.voice_service.synthesize(SynthesizeRequestDTO(text=script, user_id=user_id, tone=tone))
            return discord.File(io.BytesIO(clip.audio_bytes), filename="voice_alert.wav")
        except Exception as e:
            logger.warning("Could not synthesize voice alert: %s", e)
            return None

    task_group = app_commands.Group(name="task", description="Group task management")

    def _parse_due_date(self, due_str: str) -> Optional[datetime]:
        formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
        for fmt in formats:
            try:
                dt = datetime.strptime(due_str.strip(), fmt)
                if fmt == "%Y-%m-%d":
                    dt = dt.replace(hour=23, minute=59, second=59)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    @task_group.command(name="add", description="Assign a deliverable task to a team member")
    @app_commands.describe(
        description="Deliverable description",
        member="Team member responsible",
        due="Due date (YYYY-MM-DD or YYYY-MM-DD HH:MM)",
        verifier="Optional: accountability buddy who signs off on completion"
    )
    async def add_task(
        self,
        interaction: discord.Interaction,
        description: str,
        member: discord.Member,
        due: str,
        verifier: Optional[discord.Member] = None
    ):
        await interaction.response.defer()
        due_dt = self._parse_due_date(due)
        if not due_dt:
            await interaction.followup.send(
                "❌ **Invalid Date.** Format: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        guild_id = str(guild.id) if guild else "0"

        # Find #tasks channel if exists
        tasks_ch = discord.utils.get(guild.text_channels, name="tasks") if guild else None
        channel_id = str(tasks_ch.id) if tasks_ch else None

        try:
            dto = CreateTaskDTO(
                guild_id=guild_id,
                description=description,
                assigned_to=str(member.id),
                due_date=due_dt,
                channel_id=channel_id,
                verifier_id=str(verifier.id) if verifier else None
            )
            result = await self.service.create_task(dto)

            # Post embed to #tasks if channel exists
            view = TaskActionView(self.service)
            if tasks_ch:
                embed = build_task_embed(result)
                post_msg = await tasks_ch.send(
                    content=f"🔔 Task for {member.mention}:",
                    embed=embed,
                    view=view
                )
                await self.service.update_task_message_id(result.task_id, str(post_msg.id))

            embed = build_task_embed(result)
            await interaction.followup.send(
                content=f"✅ Task `{result.task_id}` created for {member.mention}!",
                embed=embed,
                view=view
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @task_group.command(name="complete", description="Mark an assigned task as completed")
    @app_commands.describe(task_id="The ID of the task to complete (e.g. TASK-A1B2)")
    async def complete_task(self, interaction: discord.Interaction, task_id: str):
        await interaction.response.defer()
        try:
            result = await self.service.complete_task(task_id.strip().upper())
            if result.needs_verification:
                if result.channel_id and result.message_id:
                    ch = self.bot.get_channel(int(result.channel_id))
                    if ch:
                        try:
                            msg = await ch.fetch_message(int(result.message_id))
                            await msg.edit(embed=build_task_embed(result))
                        except Exception:
                            pass
                embed = build_task_embed(result)
                await interaction.followup.send(
                    content=f"📤 Task `{result.task_id}` submitted! Awaiting verification from buddy <@{result.verifier_id}> 🔍",
                    embed=embed
                )
                return

            disabled_view = TaskActionView(self.service, is_completed=True)
            # Update ledger message if it exists
            if result.channel_id and result.message_id:
                ch = self.bot.get_channel(int(result.channel_id))
                if ch:
                    try:
                        msg = await ch.fetch_message(int(result.message_id))
                        await msg.edit(embed=build_task_embed(result), view=disabled_view)
                    except Exception:
                        pass

            embed = build_task_embed(result)
            timing_str = " (on time ⚡)" if result.is_on_time else " (late ⚠️)"
            await interaction.followup.send(
                content=f"🎉 Task `{result.task_id}` marked as completed{timing_str}!",
                embed=embed,
                view=disabled_view
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @task_group.command(name="verify", description="Sign off on a submitted deliverable as accountability buddy")
    @app_commands.describe(task_id="The ID of the task to verify (e.g. TASK-A1B2)")
    async def verify_task(self, interaction: discord.Interaction, task_id: str):
        await interaction.response.defer()
        try:
            clean_id = task_id.strip().upper()
            result = await self.service.verify_task(clean_id, str(interaction.user.id))
            disabled_view = TaskActionView(self.service, is_completed=True)
            if result.channel_id and result.message_id:
                ch = self.bot.get_channel(int(result.channel_id))
                if ch:
                    try:
                        msg = await ch.fetch_message(int(result.message_id))
                        await msg.edit(embed=build_task_embed(result), view=disabled_view)
                    except Exception:
                        pass

            embed = build_task_embed(result)
            await interaction.followup.send(
                content=f"✅ Task `{result.task_id}` verified by {interaction.user.mention}! Completion and buddy bonus recorded 🌟",
                embed=embed,
                view=disabled_view
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @task_group.command(name="extend", description="Request a deadline extension with democratic team voting")
    @app_commands.describe(
        task_id="The ID of the task to extend (e.g. TASK-A1B2)",
        new_due="Proposed new due date (YYYY-MM-DD or YYYY-MM-DD HH:MM)",
        reason="Explanation of why an extension is necessary"
    )
    async def extend_task(
        self,
        interaction: discord.Interaction,
        task_id: str,
        new_due: str,
        reason: str
    ):
        await interaction.response.defer()
        new_due_dt = self._parse_due_date(new_due)
        if not new_due_dt:
            await interaction.followup.send(
                "❌ **Invalid Date.** Format: `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        guild_id = str(guild.id) if guild else "0"
        tasks_ch = discord.utils.get(guild.text_channels, name="tasks") if guild else None

        try:
            clean_id = task_id.strip().upper()
            dto = CreateExtensionDTO(
                task_id=clean_id,
                guild_id=guild_id,
                requester_id=str(interaction.user.id),
                proposed_due_date=new_due_dt,
                reason=reason.strip()
            )
            res = await self.extension_service.request_extension(dto)
            task = await self.service.get_task(res.task_id)

            embed = build_extension_vote_embed(res, task.description)
            view = ExtensionVoteView(self.extension_service)

            if tasks_ch:
                await tasks_ch.send(
                    content=f"🗳️ **Extension Request for {interaction.user.mention}:**",
                    embed=embed,
                    view=view
                )

            await interaction.followup.send(
                content=f"🗳️ Extension request `{res.request_id}` submitted for team voting in {tasks_ch.mention if tasks_ch else 'the channel'}!",
                embed=embed,
                view=view
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @task_group.command(name="list", description="List pending tasks for this server")
    @app_commands.describe(member="Optional: filter by assigned team member")
    async def list_tasks(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id) if interaction.guild_id else "0"
        member_id = str(member.id) if member else None

        results = await self.service.get_pending_tasks(guild_id, member_id)
        if not results:
            target = f"for {member.mention}" if member else "in this server"
            await interaction.followup.send(f"✨ No pending tasks {target}!")
            return

        embed = discord.Embed(
            title=f"📋 Pending Tasks ({len(results)})",
            color=COLOR_PRIMARY,
            timestamp=datetime.now(timezone.utc)
        )
        for t in results[:15]:
            abs_ts, rel_ts = format_discord_timestamps(t.due_date)
            embed.add_field(
                name=f"`{t.task_id}` — {t.description}",
                value=f"👤 <@{t.assigned_to}> • ⏰ Due: {rel_ts}",
                inline=False
            )
        await interaction.followup.send(embed=embed)
