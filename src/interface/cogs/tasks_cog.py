"""
Task ledger Discord Cog interface.

What it does:
- Exposes /task slash commands (add, complete, list).
- Dispatches background T-24h and T-1h DM reminders.
- Formats interaction responses using discord_formatters.

What it does NOT do:
- Does NOT contain task business logic or database queries directly.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.application.dtos.task_dtos import CreateTaskDTO
from src.application.services.task_service import TaskService
from src.domain.errors import AppError
from src.interface.cogs.task_buttons import TaskActionView
from src.interface.discord_formatters import (
    build_task_embed,
    build_wall_of_shame_embed,
    format_discord_timestamps,
    COLOR_PRIMARY,
    COLOR_WARNING,
    COLOR_DANGER
)

logger = logging.getLogger("interface.cogs.tasks")

class TasksCog(commands.Cog, name="Task Ledger"):
    """Interface adapter for Task management commands and background reminders."""

    def __init__(self, bot: commands.Bot, task_service: TaskService):
        self.bot = bot
        self.service = task_service
        self.bot.add_view(TaskActionView(task_service))
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

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
        due="Due date (YYYY-MM-DD or YYYY-MM-DD HH:MM)"
    )
    async def add_task(
        self,
        interaction: discord.Interaction,
        description: str,
        member: discord.Member,
        due: str
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
                channel_id=channel_id
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

    async def _dispatch_wall_of_shame(self, now: datetime):
        """Finds overdue tasks and posts shaming notices to #wall-of-shame."""
        try:
            actions = await self.service.evaluate_overdue_tasks(now)
            for act in actions:
                guild = self.bot.get_guild(int(act.guild_id))
                if not guild:
                    continue
                shame_ch = discord.utils.get(guild.text_channels, name="wall-of-shame")
                if shame_ch:
                    embed = build_wall_of_shame_embed(act)
                    try:
                        await shame_ch.send(content=f"🚨 **WALL OF SHAME ALERT:** <@{act.user_id}>", embed=embed)
                    except Exception as e:
                        logger.warning("Could not post to #wall-of-shame in guild %s: %s", guild.id, e)
                await self.service.acknowledge_shame(act.task_id)
        except Exception as e:
            logger.error("Error in wall of shame dispatch: %s", e, exc_info=True)

    @tasks.loop(minutes=2)
    async def reminder_loop(self):
        """Dispatches automated reminders and posts overdue items to the Wall of Shame."""
        try:
            now = datetime.now(timezone.utc)
            actions = await self.service.evaluate_pending_reminders(now)
            for act in actions:
                user = self.bot.get_user(int(act.user_id))
                if not user:
                    try:
                        user = await self.bot.fetch_user(int(act.user_id))
                    except Exception:
                        continue

                abs_ts, rel_ts = format_discord_timestamps(act.due_date)
                color = COLOR_DANGER if act.reminder_tier == "1h" else COLOR_WARNING
                title = f"{'🚨 Urgent ' if act.reminder_tier == '1h' else '⏰ '}Task Reminder: {act.task_id}"

                embed = discord.Embed(
                    title=title,
                    description=f"Your task **{act.description}** is due {rel_ts}.\n\n**Deadline:** {abs_ts}",
                    color=color,
                    timestamp=now
                )
                embed.set_footer(text=f"Mark complete with: /task complete {act.task_id}")
                try:
                    await user.send(embed=embed)
                    await self.service.acknowledge_reminder(act.task_id, act.reminder_tier)
                except Exception as e:
                    logger.warning("Could not DM reminder to user %s: %s", act.user_id, e)

            # Check and post overdue tasks to the Wall of Shame
            await self._dispatch_wall_of_shame(now)
        except Exception as e:
            logger.error("Error in task reminder loop: %s", e, exc_info=True)

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()
