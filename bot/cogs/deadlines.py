import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.database import db_instance
from bot.config import DEADLINES_CHANNEL_NAME
from bot.utils.helpers import (
    generate_short_id,
    parse_datetime_input,
    get_or_create_channel,
    to_discord_timestamps
)
from bot.utils.embeds import (
    create_deadline_embed,
    COLOR_WARNING,
    COLOR_DANGER,
    COLOR_INFO
)

logger = logging.getLogger("bot.cogs.deadlines")

class DeadlinesCog(commands.Cog, name="Deadline Countdown"):
    """Manages major project deadlines, pinned countdowns, and group alert pings."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.update_deadlines_loop.start()

    def cog_unload(self):
        self.update_deadlines_loop.cancel()

    deadline_group = app_commands.Group(name="deadline", description="Project deadline and countdown commands")

    @deadline_group.command(name="add", description="Create a project milestone/deadline with pinned live countdown")
    @app_commands.describe(
        name="Name or description of the assignment / milestone",
        due="Due date and time (e.g. YYYY-MM-DD HH:MM or YYYY-MM-DD)"
    )
    async def add_deadline(self, interaction: discord.Interaction, name: str, due: str):
        await interaction.response.defer()

        due_dt = parse_datetime_input(due)
        if not due_dt:
            await interaction.followup.send(
                "❌ **Invalid Date/Time.** Format required: `YYYY-MM-DD HH:MM` (e.g. `2026-10-30 23:59`) or `YYYY-MM-DD`.",
                ephemeral=True
            )
            return

        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ This command must be run within a Discord server.", ephemeral=True)
            return

        deadlines_channel = await get_or_create_channel(
            guild,
            DEADLINES_CHANNEL_NAME,
            topic="Major project milestones, assignment due dates, and live countdowns."
        )

        if not deadlines_channel:
            await interaction.followup.send(
                f"❌ Could not find or create `#{DEADLINES_CHANNEL_NAME}` channel. Please check bot permissions.",
                ephemeral=True
            )
            return

        deadline_id = generate_short_id("DL")
        deadline_data = {
            "deadline_id": deadline_id,
            "guild_id": str(guild.id),
            "channel_id": str(deadlines_channel.id),
            "name": name,
            "due_datetime": due_dt.isoformat()
        }

        embed = create_deadline_embed(deadline_data)
        posted_message = await deadlines_channel.send(content=f"📌 **New Milestone Scheduled:**", embed=embed)

        # Pin the message if bot has manage_messages permission
        try:
            if deadlines_channel.permissions_for(guild.me).manage_messages:
                await posted_message.pin()
        except Exception as e:
            logger.warning(f"Could not pin deadline message: {e}")

        # Store deadline in database
        await db_instance.create_deadline(
            deadline_id=deadline_id,
            guild_id=str(guild.id),
            channel_id=str(deadlines_channel.id),
            message_id=str(posted_message.id),
            name=name,
            due_datetime=due_dt.isoformat()
        )

        abs_ts, rel_ts = to_discord_timestamps(due_dt)
        await interaction.followup.send(
            content=f"🎯 Milestone **{name}** (`{deadline_id}`) scheduled for {abs_ts} ({rel_ts}) and pinned in {deadlines_channel.mention}!"
        )

    @deadline_group.command(name="list", description="List all upcoming deadlines and countdowns")
    async def list_deadlines(self, interaction: discord.Interaction):
        await interaction.response.defer()

        guild_id = str(interaction.guild_id) if interaction.guild_id else None
        deadlines = await db_instance.get_active_deadlines(guild_id)

        if not deadlines:
            await interaction.followup.send("✨ No active project deadlines found. Add one with `/deadline add`!")
            return

        embed = discord.Embed(
            title=f"🎯 Upcoming Project Milestones ({len(deadlines)})",
            color=COLOR_INFO,
            timestamp=datetime.now(timezone.utc)
        )

        for d in deadlines[:10]:
            due_dt = datetime.fromisoformat(d["due_datetime"])
            abs_ts, rel_ts = to_discord_timestamps(due_dt)
            embed.add_field(
                name=f"`{d['deadline_id']}` — {d['name']}",
                value=f"📅 {abs_ts}\n⏳ {rel_ts}",
                inline=False
            )

        await interaction.followup.send(embed=embed)

    @deadline_group.command(name="complete", description="Mark a project milestone/deadline as completed")
    @app_commands.describe(deadline_id="ID of the deadline to complete (e.g. DL-A1B2)")
    async def complete_deadline(self, interaction: discord.Interaction, deadline_id: str):
        await interaction.response.defer()

        dl = await db_instance.get_deadline(deadline_id.strip().upper())
        if not dl:
            await interaction.followup.send(f"❌ Deadline `{deadline_id}` not found.", ephemeral=True)
            return

        await db_instance.mark_deadline_completed(dl["deadline_id"])

        # Try unpinning or editing the message
        try:
            ch = self.bot.get_channel(int(dl["channel_id"]))
            if ch and dl.get("message_id"):
                msg = await ch.fetch_message(int(dl["message_id"]))
                embed = msg.embeds[0] if msg.embeds else create_deadline_embed(dl)
                embed.title = f"✅ COMPLETED: {dl['name']}"
                embed.color = discord.Color.green()
                await msg.edit(embed=embed)
                if ch.permissions_for(interaction.guild.me).manage_messages and msg.pinned:
                    await msg.unpin()
        except Exception as e:
            logger.warning(f"Could not update deadline message upon completion: {e}")

        await interaction.followup.send(f"🎉 Milestone **{dl['name']}** (`{dl['deadline_id']}`) marked as completed!")

    # ------------------ Hourly Countdown & Alert Loop ------------------
    @tasks.loop(minutes=15)
    async def update_deadlines_loop(self):
        """
        Updates live countdown embed in #deadlines channel every 15 minutes,
        and triggers group alert pings at T-72h, T-24h, and T-6h.
        """
        try:
            deadlines = await db_instance.get_active_deadlines()
            now = datetime.now(timezone.utc)

            for d in deadlines:
                due_dt = datetime.fromisoformat(d["due_datetime"])
                if due_dt.tzinfo is None:
                    due_dt = due_dt.replace(tzinfo=timezone.utc)

                time_left = due_dt - now
                channel_id = int(d["channel_id"])
                channel = self.bot.get_channel(channel_id)
                if not channel:
                    try:
                        channel = await self.bot.fetch_channel(channel_id)
                    except Exception:
                        continue

                # 1. Update the pinned countdown message embed
                if d.get("message_id"):
                    try:
                        msg = await channel.fetch_message(int(d["message_id"]))
                        updated_embed = create_deadline_embed(d)
                        await msg.edit(embed=updated_embed)
                    except Exception as e:
                        logger.debug(f"Could not refresh deadline message for {d['deadline_id']}: {e}")

                # 2. Check Alert Tiers: T-72h, T-24h, T-6h
                abs_ts, rel_ts = to_discord_timestamps(due_dt)

                # T-72h (Between 24h and 72h)
                if timedelta(hours=24) < time_left <= timedelta(hours=72) and not d["reminded_72h"]:
                    ping_embed = discord.Embed(
                        title=f"⚠️ Milestone Alert: 72 Hours Remaining!",
                        description=f"**{d['name']}** is due in less than 3 days.\n\n**Deadline:** {abs_ts} ({rel_ts})\nMake sure your assigned tasks are on track!",
                        color=COLOR_INFO,
                        timestamp=now
                    )
                    await channel.send(content="@everyone", embed=ping_embed)
                    await db_instance.mark_deadline_reminded(d["deadline_id"], "72h")

                # T-24h (Between 6h and 24h)
                elif timedelta(hours=6) < time_left <= timedelta(hours=24) and not d["reminded_24h"]:
                    ping_embed = discord.Embed(
                        title=f"🚨 Milestone Alert: 24 Hours Remaining!",
                        description=f"**{d['name']}** is due tomorrow!\n\n**Deadline:** {abs_ts} ({rel_ts})\nPlease finish your deliverables and review draft submissions.",
                        color=COLOR_WARNING,
                        timestamp=now
                    )
                    await channel.send(content="@everyone", embed=ping_embed)
                    await db_instance.mark_deadline_reminded(d["deadline_id"], "24h")

                # T-6h (Between 0s and 6h)
                elif timedelta(seconds=0) < time_left <= timedelta(hours=6) and not d["reminded_6h"]:
                    ping_embed = discord.Embed(
                        title=f"🔥 CRITICAL DEADLINE ALERT: 6 Hours Remaining!",
                        description=f"Final countdown for **{d['name']}**!\n\n**Deadline:** {abs_ts} ({rel_ts})\nFinal submission files should be uploaded immediately.",
                        color=COLOR_DANGER,
                        timestamp=now
                    )
                    await channel.send(content="@everyone", embed=ping_embed)
                    await db_instance.mark_deadline_reminded(d["deadline_id"], "6h")

        except Exception as e:
            logger.error(f"Error in deadline update loop: {e}", exc_info=True)

    @update_deadlines_loop.before_loop
    async def before_deadlines_loop(self):
        await self.bot.wait_until_ready()

async def setup(bot: commands.Bot):
    await bot.add_cog(DeadlinesCog(bot))
