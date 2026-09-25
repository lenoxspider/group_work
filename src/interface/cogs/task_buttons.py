"""
Task interactive card buttons interface.

What it does:
- Provides persistent discord.ui.View buttons for task embeds: Nudge, In-Progress, Complete.
- Enforces permissions (assignee / admin check) and 30-minute nudge cooldown.
- Dispatches state updates through TaskService and refreshes Discord embeds.

What it does NOT do:
- Does NOT execute direct database queries or domain calculations.
"""

import re
import logging
from datetime import datetime, timezone
from typing import Optional, Dict
import discord

from src.application.services.task_service import TaskService
from src.interface.discord_formatters import build_task_embed
from src.domain.errors import AppError

logger = logging.getLogger("interface.cogs.task_buttons")

NUDGE_COOLDOWN_SECONDS = 1800  # 30 minutes

class TaskActionView(discord.ui.View):
    """Persistent action buttons for task ledger embeds."""

    # In-memory cooldown cache: task_id -> datetime of last nudge
    _nudge_cooldowns: Dict[str, datetime] = {}

    def __init__(self, task_service: TaskService, is_completed: bool = False):
        super().__init__(timeout=None)
        self.service = task_service
        if is_completed:
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True

    def _extract_task_id(self, message: discord.Message) -> Optional[str]:
        """Extracts task_id from the embed title or footer."""
        if not message.embeds:
            return None
        embed = message.embeds[0]
        if embed.title:
            match = re.search(r"Task:\s*([A-Za-z0-9\-]+)", embed.title)
            if match:
                return match.group(1).strip()
        if embed.footer and embed.footer.text:
            match = re.search(r"Task ID:\s*([A-Za-z0-9\-]+)", embed.footer.text)
            if match:
                return match.group(1).strip()
        return None

    def _is_authorized(self, member: discord.Member, assigned_to_id: str) -> bool:
        """Verifies if member is the assignee or has server moderation rights."""
        if str(member.id) == assigned_to_id:
            return True
        perms = member.guild_permissions
        return perms.manage_messages or perms.administrator

    @discord.ui.button(
        label="Nudge",
        style=discord.ButtonStyle.secondary,
        emoji="🔔",
        custom_id="task_action_btn:nudge"
    )
    async def nudge_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        task_id = self._extract_task_id(interaction.message)
        if not task_id:
            await interaction.followup.send("❌ Could not identify task ID from card.", ephemeral=True)
            return

        now = datetime.now(timezone.utc)
        last_nudge = self._nudge_cooldowns.get(task_id)
        if last_nudge:
            elapsed = (now - last_nudge).total_seconds()
            if elapsed < NUDGE_COOLDOWN_SECONDS:
                remaining_mins = max(1, int((NUDGE_COOLDOWN_SECONDS - elapsed) // 60))
                await interaction.followup.send(
                    f"⏳ This task was already nudged recently. Cooldown remaining: **{remaining_mins} min(s)**.",
                    ephemeral=True
                )
                return

        try:
            task = await self.service.get_task(task_id)
            if task.is_completed:
                await interaction.followup.send("✨ Task is already completed! No nudge needed.", ephemeral=True)
                return

            self._nudge_cooldowns[task_id] = now
            channel = interaction.channel
            if channel:
                await channel.send(
                    f"🔔 <@{task.assigned_to}>, friendly nudge from {interaction.user.mention} on task "
                    f"`{task.task_id}` (**{task.description}**)!"
                )
            await interaction.followup.send(f"✅ Nudge sent to <@{task.assigned_to}>!", ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @discord.ui.button(
        label="In Progress",
        style=discord.ButtonStyle.primary,
        emoji="🔄",
        custom_id="task_action_btn:progress"
    )
    async def progress_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        task_id = self._extract_task_id(interaction.message)
        if not task_id:
            await interaction.followup.send("❌ Could not identify task ID from card.", ephemeral=True)
            return

        try:
            task = await self.service.get_task(task_id)
            if task.is_completed:
                await interaction.followup.send("✨ Task is already marked completed.", ephemeral=True)
                return

            if isinstance(interaction.user, discord.Member) and not self._is_authorized(interaction.user, task.assigned_to):
                await interaction.followup.send(
                    f"❌ Only the assignee (<@{task.assigned_to}>) or a team admin can update task progress.",
                    ephemeral=True
                )
                return

            updated_dto = await self.service.toggle_in_progress(task_id)
            await interaction.message.edit(embed=build_task_embed(updated_dto))
            status_name = "In Progress ⚙️" if updated_dto.is_in_progress else "Pending ⏳"
            await interaction.followup.send(f"🔄 Task status updated to **{status_name}**.", ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @discord.ui.button(
        label="Complete",
        style=discord.ButtonStyle.success,
        emoji="✅",
        custom_id="task_action_btn:complete"
    )
    async def complete_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        task_id = self._extract_task_id(interaction.message)
        if not task_id:
            await interaction.followup.send("❌ Could not identify task ID from card.", ephemeral=True)
            return

        try:
            task = await self.service.get_task(task_id)
            if task.is_completed:
                await interaction.followup.send("✨ Task is already completed.", ephemeral=True)
                return

            if isinstance(interaction.user, discord.Member) and not self._is_authorized(interaction.user, task.assigned_to):
                await interaction.followup.send(
                    f"❌ Only the assignee (<@{task.assigned_to}>) or a team admin can mark this completed.",
                    ephemeral=True
                )
                return

            result_dto = await self.service.complete_task(task_id)
            disabled_view = TaskActionView(self.service, is_completed=True)
            await interaction.message.edit(embed=build_task_embed(result_dto), view=disabled_view)

            timing = "on time ⚡" if result_dto.is_on_time else "late ⚠️"
            await interaction.channel.send(
                f"🎉 Task `{result_dto.task_id}` marked completed by {interaction.user.mention} ({timing})!"
            )
            await interaction.followup.send(f"✅ Marked task `{result_dto.task_id}` completed!", ephemeral=True)
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @discord.ui.button(
        label="Extend",
        style=discord.ButtonStyle.secondary,
        emoji="⏳",
        custom_id="task_action_btn:extend"
    )
    async def extend_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        task_id = self._extract_task_id(interaction.message)
        if not task_id:
            await interaction.followup.send("❌ Could not identify task ID from card.", ephemeral=True)
            return

        try:
            task = await self.service.get_task(task_id)
            if task.is_completed:
                await interaction.followup.send("✨ Task is already completed.", ephemeral=True)
                return

            if isinstance(interaction.user, discord.Member) and not self._is_authorized(interaction.user, task.assigned_to):
                await interaction.followup.send(
                    f"❌ Only the assignee (<@{task.assigned_to}>) or a team admin can request an extension.",
                    ephemeral=True
                )
                return

            await interaction.followup.send(
                f"⏳ **Request Deadline Extension for `{task.task_id}`**\n"
                f"To initiate team voting, run:\n"
                f"`/task extend task_id:{task.task_id} new_due:YYYY-MM-DD reason:<why you need more time>`",
                ephemeral=True
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

