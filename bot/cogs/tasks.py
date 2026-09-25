import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.database import db_instance
from bot.config import TASKS_CHANNEL_NAME
from bot.utils.helpers import (
    generate_short_id,
    parse_datetime_input,
    get_or_create_channel,
    to_discord_timestamps
)
from bot.utils.embeds import (
    create_task_embed,
    COLOR_SUCCESS,
    COLOR_WARNING,
    COLOR_DANGER,
    COLOR_PRIMARY
)

logger = logging.getLogger("bot.cogs.tasks")

class TaskLedgerCog(commands.Cog, name="Task Ledger"):
    """Manages group task assignments, reminders, and completions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    # ------------------ Slash Commands ------------------
    task_group = app_commands.Group(name="task", description="Group task management commands")

    @task_group.command(name="add", description="Add and assign a new task to a team member")
    @app_commands.describe(
        description="Brief description of the deliverable or task",
        member="Team member responsible for this task",
        due="Due date (e.g. YYYY-MM-DD or YYYY-MM-DD HH:MM)"
    )
    async def add_task(
        self,
        interaction: discord.Interaction,
        description: str,
        member: discord.Member,
        due: str
    ):
        await interaction.response.defer(ephemeral=False)

        due_dt = parse_datetime_input(due)
        if not due_dt:
            await interaction.followup.send(
                "❌ **Invalid Date Format.** Please use `YYYY-MM-DD` (e.g. `2026-10-15`) or `YYYY-MM-DD HH:MM`.",
                ephemeral=True
            )
            return

        task_id = generate_short_id("TASK")
        guild = interaction.guild

        # Locate or create the #tasks channel
        tasks_channel = None
        if guild:
            tasks_channel = await get_or_create_channel(
                guild,
                TASKS_CHANNEL_NAME,
                topic="Group task ledger and real-time deliverables tracking."
            )

        task_dict = {
            "task_id": task_id,
            "guild_id": str(guild.id) if guild else None,
            "channel_id": str(tasks_channel.id) if tasks_channel else None,
            "message_id": None,
            "description": description,
            "assigned_to": str(member.id),
            "due_date": due_dt.isoformat(),
            "completed_at": None
        }

        posted_msg = None
        if tasks_channel:
            embed = create_task_embed(task_dict, assignee=member)
            try:
                posted_msg = await tasks_channel.send(content=f"🔔 New Task for {member.mention}:", embed=embed)
                task_dict["message_id"] = str(posted_msg.id)
            except Exception as e:
                logger.error(f"Failed to post task embed in #{TASKS_CHANNEL_NAME}: {e}")

        # Store in SQLite database
        await db_instance.create_task(
            task_id=task_id,
            guild_id=str(guild.id) if guild else "0",
            channel_id=str(tasks_channel.id) if tasks_channel else None,
            message_id=str(posted_msg.id) if posted_msg else None,
            description=description,
            assigned_to=str(member.id),
            due_date=due_dt.isoformat()
        )

        # Notify assignee via DM if possible
        abs_ts, rel_ts = to_discord_timestamps(due_dt)
        try:
            dm_embed = discord.Embed(
                title=f"📋 You were assigned a new task: {task_id}",
                description=f"**{description}**\n\n**Server:** {guild.name if guild else 'Group'}\n**Due:** {abs_ts} ({rel_ts})",
                color=COLOR_PRIMARY
            )
            dm_embed.set_footer(text=f"Mark as complete in server using: /task complete {task_id}")
            await member.send(embed=dm_embed)
        except Exception:
            logger.info(f"Could not send DM to {member.name} (user may have DMs closed).")

        reply_embed = create_task_embed(task_dict, assignee=member)
        await interaction.followup.send(
            content=f"✅ Task `{task_id}` created and assigned to {member.mention}!",
            embed=reply_embed
        )

    @task_group.command(name="complete", description="Mark an assigned task as completed")
    @app_commands.describe(task_id="The ID of the task to mark as complete (e.g. TASK-A1B2)")
    async def complete_task(self, interaction: discord.Interaction, task_id: str):
        await interaction.response.defer()

        task = await db_instance.get_task(task_id.strip().upper())
        if not task:
            await interaction.followup.send(f"❌ Task `{task_id}` not found. Check the ID and try again.", ephemeral=True)
            return

        if task.get("completed_at"):
            await interaction.followup.send(f"ℹ️ Task `{task_id}` is already marked as completed.", ephemeral=True)
            return

        updated_task = await db_instance.complete_task(task["task_id"])

        # Update the original message in #tasks if available
        if updated_task.get("channel_id") and updated_task.get("message_id"):
            try:
                ch = self.bot.get_channel(int(updated_task["channel_id"]))
                if ch:
                    msg = await ch.fetch_message(int(updated_task["message_id"]))
                    assignee = interaction.guild.get_member(int(updated_task["assigned_to"])) if interaction.guild else None
                    new_embed = create_task_embed(updated_task, assignee=assignee)
                    await msg.edit(embed=new_embed)
            except Exception as e:
                logger.warning(f"Could not update original ledger message: {e}")

        # Post celebration embed
        embed = discord.Embed(
            title="🎉 Task Completed!",
            description=f"Task `{updated_task['task_id']}` (**{updated_task['description']}**) has been marked complete by {interaction.user.mention}.",
            color=COLOR_SUCCESS,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text="Contribution report updated.")
        await interaction.followup.send(embed=embed)

    @task_group.command(name="list", description="List all pending tasks for this group or member")
    @app_commands.describe(member="Optional: filter tasks by assigned member")
    async def list_tasks(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        await interaction.response.defer()

        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        pending_tasks = await db_instance.get_pending_tasks(guild_id)

        if member:
            pending_tasks = [t for t in pending_tasks if t["assigned_to"] == str(member.id)]

        if not pending_tasks:
            target_str = f"for {member.mention}" if member else "in this server"
            await interaction.followup.send(f"✨ No pending tasks {target_str}! Everything is up to date.")
            return

        embed = discord.Embed(
            title=f"📋 Pending Tasks ({len(pending_tasks)})",
            color=COLOR_PRIMARY,
            timestamp=datetime.now(timezone.utc)
        )

        for t in pending_tasks[:15]:
            due_dt = datetime.fromisoformat(t["due_date"])
            _, rel_ts = to_discord_timestamps(due_dt)
            assignee_str = f"<@{t['assigned_to']}>"
            embed.add_field(
                name=f"`{t['task_id']}` - {t['description']}",
                value=f"👤 {assignee_str} • ⏰ Due: {rel_ts}",
                inline=False
            )

        if len(pending_tasks) > 15:
            embed.set_footer(text=f"Showing 15 of {len(pending_tasks)} pending tasks.")

        await interaction.followup.send(embed=embed)

    # ------------------ Automated Reminders Loop ------------------
    @tasks.loop(minutes=2)
    async def reminder_loop(self):
        """Runs periodically to send T-24h and T-1h DM reminders to task assignees."""
        try:
            pending = await db_instance.get_pending_tasks()
            now = datetime.now(timezone.utc)

            for task in pending:
                due_dt = datetime.fromisoformat(task["due_date"])
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=timezone.utc)

                time_left = due_dt - now
                user_id = int(task["assigned_to"])
                user = self.bot.get_user(user_id)
                if not user:
                    try:
                        user = await self.bot.fetch_user(user_id)
                    except Exception:
                        continue

                # T-24h Reminder (between 1 hour and 24 hours left, not yet reminded)
                if timedelta(hours=1) < time_left <= timedelta(hours=24) and not task["reminded_24h"]:
                    try:
                        abs_ts, rel_ts = to_discord_timestamps(due_dt)
                        embed = discord.Embed(
                            title=f"⏰ Task Reminder (24 Hours Remaining): {task['task_id']}",
                            description=f"Your assigned task **{task['description']}** is due in less than 24 hours.\n\n**Deadline:** {abs_ts} ({rel_ts})",
                            color=COLOR_WARNING,
                            timestamp=now
                        )
                        embed.set_footer(text="Mark as complete using: /task complete " + task["task_id"])
                        await user.send(embed=embed)
                        await db_instance.mark_task_reminded(task["task_id"], "24h")
                        logger.info(f"Sent T-24h reminder for task {task['task_id']} to user {user_id}")
                    except Exception as e:
                        logger.warning(f"Could not send T-24h reminder to user {user_id}: {e}")

                # T-1h Urgent Reminder (less than or equal to 1 hour left, not yet reminded)
                elif timedelta(seconds=0) < time_left <= timedelta(hours=1) and not task["reminded_1h"]:
                    try:
                        abs_ts, rel_ts = to_discord_timestamps(due_dt)
                        embed = discord.Embed(
                            title=f"🚨 Urgent Task Reminder (1 Hour Remaining): {task['task_id']}",
                            description=f"Your assigned task **{task['description']}** is due in less than 1 hour!\n\n**Deadline:** {abs_ts} ({rel_ts})",
                            color=COLOR_DANGER,
                            timestamp=now
                        )
                        embed.set_footer(text="Mark as complete using: /task complete " + task["task_id"])
                        await user.send(embed=embed)
                        await db_instance.mark_task_reminded(task["task_id"], "1h")
                        logger.info(f"Sent T-1h reminder for task {task['task_id']} to user {user_id}")
                    except Exception as e:
                        logger.warning(f"Could not send T-1h reminder to user {user_id}: {e}")

        except Exception as e:
            logger.error(f"Error in task reminder loop: {e}", exc_info=True)

    @reminder_loop.before_loop
    async def before_reminder_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(TaskLedgerCog(bot))
