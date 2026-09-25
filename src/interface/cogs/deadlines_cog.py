"""
Milestone and deadline Discord Cog interface.

What it does:
- Exposes /deadline slash commands (add, complete, list).
- Manages pinned countdown messages in #deadlines channel.
- Dispatches T-72h, T-24h, and T-6h milestone alert pings.

What it does NOT do:
- Does NOT execute milestone business logic or database queries.
"""

import logging
from datetime import datetime, timezone
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.application.dtos.deadline_dtos import CreateDeadlineDTO
from src.application.services.deadline_service import DeadlineService
from src.domain.errors import AppError
from src.interface.discord_formatters import (
    build_deadline_embed,
    format_discord_timestamps,
    COLOR_INFO,
    COLOR_WARNING,
    COLOR_DANGER
)

logger = logging.getLogger("interface.cogs.deadlines")

class DeadlinesCog(commands.Cog, name="Milestones"):
    """Interface adapter for Deadline countdown commands and alert loops."""

    def __init__(self, bot: commands.Bot, deadline_service: DeadlineService):
        self.bot = bot
        self.service = deadline_service
        self.countdown_loop.start()

    def cog_unload(self):
        self.countdown_loop.cancel()

    deadline_group = app_commands.Group(name="deadline", description="Project milestone countdowns")

    def _parse_due_datetime(self, date_str: str) -> Optional[datetime]:
        formats = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"]
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                if fmt == "%Y-%m-%d":
                    dt = dt.replace(hour=23, minute=59, second=59)
                return dt.replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    @deadline_group.command(name="add", description="Schedule a major project milestone with pinned countdown")
    @app_commands.describe(
        name="Milestone name or deliverable title",
        due="Due date and time (YYYY-MM-DD HH:MM or YYYY-MM-DD)"
    )
    async def add_deadline(self, interaction: discord.Interaction, name: str, due: str):
        await interaction.response.defer()
        due_dt = self._parse_due_datetime(due)
        if not due_dt:
            await interaction.followup.send(
                "❌ **Invalid Date.** Please use `YYYY-MM-DD HH:MM` or `YYYY-MM-DD`.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Must be executed in a server.", ephemeral=True)
            return

        deadlines_ch = discord.utils.get(guild.text_channels, name="deadlines")
        if not deadlines_ch:
            await interaction.followup.send(
                "❌ `#deadlines` channel not found. Please run `/setup` first.",
                ephemeral=True
            )
            return

        try:
            # 1. Post initial pinned message placeholder
            msg = await deadlines_ch.send(content="⏳ Initializing countdown milestone...")
            try:
                if deadlines_ch.permissions_for(guild.me).manage_messages:
                    await msg.pin()
            except Exception:
                pass

            dto = CreateDeadlineDTO(
                guild_id=str(guild.id),
                channel_id=str(deadlines_ch.id),
                message_id=str(msg.id),
                name=name,
                due_datetime=due_dt
            )
            result = await self.service.schedule_deadline(dto)

            # Update the pinned message with the formatted embed
            await msg.edit(content=None, embed=build_deadline_embed(result))

            abs_ts, rel_ts = format_discord_timestamps(result.due_datetime)
            await interaction.followup.send(
                content=f"🎯 Milestone **{result.name}** (`{result.deadline_id}`) scheduled for {abs_ts} ({rel_ts}) and pinned in {deadlines_ch.mention}!"
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @deadline_group.command(name="complete", description="Mark a project milestone as finished")
    @app_commands.describe(deadline_id="ID of the deadline to mark complete (e.g. DL-A1B2)")
    async def complete_deadline(self, interaction: discord.Interaction, deadline_id: str):
        await interaction.response.defer()
        try:
            result = await self.service.complete_deadline(deadline_id.strip().upper())
            ch = self.bot.get_channel(int(result.channel_id))
            if ch:
                try:
                    msg = await ch.fetch_message(int(result.message_id))
                    embed = build_deadline_embed(result)
                    embed.title = f"✅ FINISHED: {result.name}"
                    embed.color = discord.Color.green()
                    await msg.edit(embed=embed)
                    if msg.pinned and ch.permissions_for(interaction.guild.me).manage_messages:
                        await msg.unpin()
                except Exception:
                    pass

            await interaction.followup.send(f"🎉 Milestone **{result.name}** marked as completed!")
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)

    @deadline_group.command(name="list", description="List all active project milestones")
    async def list_deadlines(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id) if interaction.guild_id else "0"
        deadlines = await self.service.get_active_deadlines(guild_id)

        if not deadlines:
            await interaction.followup.send("✨ No active project milestones scheduled!")
            return

        embed = discord.Embed(
            title=f"🎯 Upcoming Project Milestones ({len(deadlines)})",
            color=COLOR_INFO,
            timestamp=datetime.now(timezone.utc)
        )
        for d in deadlines[:10]:
            abs_ts, rel_ts = format_discord_timestamps(d.due_datetime)
            embed.add_field(
                name=f"`{d.deadline_id}` — {d.name}",
                value=f"📅 {abs_ts}\n⏳ {rel_ts}",
                inline=False
            )
        await interaction.followup.send(embed=embed)

    @tasks.loop(minutes=15)
    async def countdown_loop(self):
        """Refreshes pinned countdown messages and broadcasts group alerts."""
        try:
            now = datetime.now(timezone.utc)
            actions = await self.service.evaluate_pending_alerts(now)

            for act in actions:
                ch = self.bot.get_channel(int(act.channel_id))
                if not ch:
                    try:
                        ch = await self.bot.fetch_channel(int(act.channel_id))
                    except Exception:
                        continue

                abs_ts, rel_ts = format_discord_timestamps(act.due_datetime)
                if act.alert_tier == "6h":
                    color, title = COLOR_DANGER, "🔥 CRITICAL ALERT: 6 Hours Remaining!"
                elif act.alert_tier == "24h":
                    color, title = COLOR_WARNING, "🚨 Milestone Alert: 24 Hours Remaining!"
                else:
                    color, title = COLOR_INFO, "⚠️ Milestone Alert: 72 Hours Remaining!"

                embed = discord.Embed(
                    title=title,
                    description=f"**{act.name}** is due {rel_ts}.\n\n**Deadline:** {abs_ts}",
                    color=color,
                    timestamp=now
                )
                await ch.send(content="@everyone", embed=embed)
                await self.service.acknowledge_alert(act.deadline_id, act.alert_tier)
        except Exception as e:
            logger.error("Error in countdown alert loop: %s", e, exc_info=True)

    @countdown_loop.before_loop
    async def before_countdown_loop(self):
        await self.bot.wait_until_ready()
