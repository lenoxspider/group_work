"""
Task background reminder and shaming loop Cog.

What it does:
- Runs automated 2-minute periodic checks for escalating T-24h, T-6h, and T-1h reminders.
- Posts overdue tasks to #wall-of-shame with optional voice alerts.
- Integrates with Squid Game engine to eliminate enrolled players with terminal overdue tasks.

What it does NOT do:
- Does NOT execute slash commands directly.
- Does NOT perform database I/O directly.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Optional
import discord
from discord.ext import commands, tasks

from src.application.services.task_service import TaskService
from src.application.services.preference_service import PreferenceService
from src.application.services.voice_service import VoiceService
from src.application.services.squid_service import SquidService
from src.application.dtos.voice_dtos import SynthesizeRequestDTO
from src.interface.discord_formatters import (
    build_wall_of_shame_embed,
    format_discord_timestamps,
    COLOR_WARNING,
    COLOR_DANGER
)
from src.interface.squid_formatters import build_squid_elimination_embed

logger = logging.getLogger("interface.cogs.task_reminders")

class TaskReminderCog(commands.Cog, name="Task Reminder Loop"):
    """Background loop manager for task notifications, escalation, and Squid Game elimination."""

    def __init__(
        self,
        bot: commands.Bot,
        task_service: TaskService,
        preference_service: Optional[PreferenceService] = None,
        voice_service: Optional[VoiceService] = None,
        squid_service: Optional[SquidService] = None
    ):
        self.bot = bot
        self.service = task_service
        self.preference_service = preference_service
        self.voice_service = voice_service
        self.squid_service = squid_service
        self.reminder_loop.start()

    def cog_unload(self):
        self.reminder_loop.cancel()

    async def _try_generate_voice_file(self, script: str, user_id: str, tone: str = "drill_sergeant") -> Optional[discord.File]:
        if not self.voice_service or not script:
            return None
        try:
            clip = await self.voice_service.synthesize(SynthesizeRequestDTO(text=script, user_id=user_id, tone=tone))
            return discord.File(io.BytesIO(clip.audio_bytes), filename="voice_alert.wav")
        except Exception as e:
            logger.warning("Could not synthesize voice alert: %s", e)
            return None

    async def _dispatch_wall_of_shame(self, now: datetime):
        """Finds overdue tasks and posts shaming notices to #wall-of-shame and checks Squid Game elimination."""
        try:
            actions = await self.service.evaluate_overdue_tasks(now)
            for act in actions:
                guild = self.bot.get_guild(int(act.guild_id))
                if not guild:
                    continue

                shame_ch = discord.utils.get(guild.text_channels, name="wall-of-shame")
                if shame_ch:
                    embed = build_wall_of_shame_embed(act)
                    v_script = self.voice_service.generate_task_reminder_script(
                        act.task_id, act.description, f"<@{act.user_id}>", hours_overdue=act.hours_overdue
                    ) if self.voice_service else ""
                    v_file = await self._try_generate_voice_file(v_script, act.user_id) if v_script else None
                    try:
                        await shame_ch.send(content=f"🚨 **WALL OF SHAME ALERT:** <@{act.user_id}>", embed=embed, file=v_file)
                    except Exception as e:
                        logger.warning("Could not post to #wall-of-shame in guild %s: %s", guild.id, e)

                # Squid Game Integration: eliminate enrolled player on overdue task
                if self.squid_service:
                    player = await self.squid_service.get_player(act.guild_id, act.user_id)
                    if player and player.is_alive:
                        elim = await self.squid_service.eliminate_player(
                            act.guild_id,
                            act.user_id,
                            reason=f"Task {act.task_id} overdue by {act.hours_overdue}h"
                        )
                        game_hub = discord.utils.get(guild.text_channels, name="game-hub") or shame_ch
                        if game_hub:
                            squid_embed = build_squid_elimination_embed(elim)
                            s_file = discord.File(io.BytesIO(elim.audio_bytes), filename="elimination.wav") if elim.audio_bytes else None
                            try:
                                await game_hub.send(
                                    content=f"💀 **SQUID GAME ELIMINATION:** <@{act.user_id}> has been terminated for missing task {act.task_id}!",
                                    embed=squid_embed,
                                    file=s_file
                                )
                            except Exception as e:
                                logger.warning("Could not dispatch Squid Game elimination notice: %s", e)

                await self.service.acknowledge_shame(act.task_id)
        except Exception as e:
            logger.error("Error in wall of shame dispatch: %s", e, exc_info=True)

    @tasks.loop(minutes=2)
    async def reminder_loop(self):
        """Dispatches automated escalating reminders and posts overdue items to the Wall of Shame."""
        try:
            now = datetime.now(timezone.utc)
            actions = await self.service.evaluate_pending_reminders(now)
            for act in actions:
                abs_ts, rel_ts = format_discord_timestamps(act.due_date)

                # Tier 2 (T-6h): Channel Escalation Ping
                if act.reminder_tier == "6h":
                    guild = self.bot.get_guild(int(act.guild_id))
                    if guild:
                        tasks_ch = discord.utils.get(guild.text_channels, name="tasks")
                        if tasks_ch:
                            embed = discord.Embed(
                                title=f"⚠️ Escalation Alert (T-6h): {act.task_id}",
                                description=f"Task **{act.description}** assigned to <@{act.user_id}> is due in under 6 hours!\n\n**Deadline:** {abs_ts} ({rel_ts})",
                                color=COLOR_WARNING,
                                timestamp=now
                            )
                            embed.set_footer(text=f"Complete: /task complete {act.task_id} • Or request extension: /task extend")
                            try:
                                await tasks_ch.send(content=f"⚠️ Attention <@{act.user_id}>:", embed=embed)
                            except Exception:
                                pass
                    await self.service.acknowledge_reminder(act.task_id, act.reminder_tier)
                    continue

                # Tier 1 (T-24h) & Tier 3 (T-1h): Direct Message
                if self.preference_service:
                    is_quiet = await self.preference_service.is_in_quiet_hours(act.guild_id, act.user_id, now)
                    if is_quiet:
                        logger.info("Suppressing DM reminder for user %s during quiet hours", act.user_id)
                        continue

                user = self.bot.get_user(int(act.user_id))
                if not user:
                    try:
                        user = await self.bot.fetch_user(int(act.user_id))
                    except Exception:
                        continue

                color = COLOR_DANGER if act.reminder_tier == "1h" else COLOR_WARNING
                title = f"{'🚨 Urgent ' if act.reminder_tier == '1h' else '⏰ '}Task Reminder: {act.task_id}"

                embed = discord.Embed(
                    title=title,
                    description=f"Your task **{act.description}** is due {rel_ts}.\n\n**Deadline:** {abs_ts}",
                    color=color,
                    timestamp=now
                )
                embed.set_footer(text=f"Complete: /task complete {act.task_id} • Request extension: /task extend")
                v_file = None
                if self.voice_service and act.reminder_tier == "1h":
                    v_script = self.voice_service.generate_task_reminder_script(
                        act.task_id, act.description, user.display_name, is_urgent=True
                    )
                    v_file = await self._try_generate_voice_file(v_script, act.user_id)

                try:
                    await user.send(embed=embed, file=v_file)
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
