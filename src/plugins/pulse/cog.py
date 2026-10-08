"""Pulse Cog - the scheduler, the audience trigger, and the win judges."""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.interface.channel_router import ChannelRouter
from src.plugins.pulse.domain import (
    PULSE_COOLDOWN_MINUTES,
    PULSE_PRIZE_SPI,
)
from src.plugins.pulse.modules import normalize
from src.plugins.pulse.service import PulseService

logger = logging.getLogger("plugins.pulse.cog")


class PulseCog(commands.Cog, name="Pulse"):
    pulse = app_commands.Group(name="pulse", description="The pulse - bot-fired moments")

    def __init__(
        self,
        bot: commands.Bot,
        service: PulseService,
        channel_router: Optional[ChannelRouter] = None,
    ):
        self.bot = bot
        self.service = service
        self.channel_router = channel_router
        self.pulse_loop.start()

    def cog_unload(self):
        self.pulse_loop.cancel()

    async def _pulse_channel(self, guild: discord.Guild):
        if self.channel_router:
            return await self.channel_router.resolve(guild, "pulse")
        return discord.utils.get(guild.text_channels, name="pulse")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        gid = str(message.guild.id)
        self.bot.presence.note(gid)

        pulse = self.service.active_pulse(gid)
        if not pulse or pulse.mode != "message":
            return
        if str(message.channel.id) != pulse.channel_id:
            return
        if normalize(message.content) not in pulse.accept:
            return
        self.service.clear(gid)
        await self.service.grant(gid, str(message.author.id))
        try:
            await message.reply(f"🏆 Credited — **+{PULSE_PRIZE_SPI} spi** · win *{pulse.label}*.")
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not payload.guild_id:
            return
        if self.bot.user and payload.user_id == self.bot.user.id:
            return
        # Reacting is presence too: a jury voting on a Snap Trial counts as an
        # audience just as much as someone typing.
        self.bot.presence.note(str(payload.guild_id))
        pulse = self.service.active_pulse(str(payload.guild_id))
        if not pulse or pulse.mode != "reaction":
            return
        if str(payload.message_id) != pulse.message_id:
            return
        if str(payload.emoji) != pulse.answer:
            return
        self.service.clear(str(payload.guild_id))
        await self.service.grant(str(payload.guild_id), str(payload.user_id))
        channel = self.bot.get_channel(int(pulse.channel_id))
        if channel:
            try:
                await channel.send(
                    f"🏆 <@{payload.user_id}> — fastest hand in the collective! "
                    f"**+{PULSE_PRIZE_SPI} spi** · won *{pulse.label}*."
                )
            except Exception:
                pass

    def _minutes_since_activity(self, guild_id: str) -> Optional[float]:
        """Minutes since anyone spoke or reacted, or None if we have never seen any."""
        return self.bot.presence.minutes_since(guild_id)

    def _audience_present(self, guild_id: str) -> bool:
        """True when someone is demonstrably around to see a pulse land.

        This used to be the opposite: the pulse fired once the hall had gone
        *quiet*, on the theory that silence meant people lurking who needed a
        nudge. In practice it fired into an empty room at 03:00, and fired on
        the first loop tick after every restart because no activity had been
        recorded yet. A pulse nobody claims trains people to ignore #pulse, so
        the bot now waits for proof of life instead.
        """
        return self.bot.presence.audience_present(guild_id)

    async def _should_fire(self, guild_id: str) -> bool:
        secs = await self.service.last_fired_seconds(guild_id)
        if secs is not None and secs < PULSE_COOLDOWN_MINUTES * 60:
            return False
        return self._audience_present(guild_id)

    @tasks.loop(minutes=2)
    async def pulse_loop(self):
        for guild in self.bot.guilds:
            gid = str(guild.id)
            pulse = self.service.active_pulse(gid)
            if pulse:
                if pulse.is_expired():
                    self.service.clear(gid)
                    ch = self.bot.get_channel(int(pulse.channel_id))
                    if ch:
                        try:
                            if pulse.mode == "vote":
                                msg = await ch.fetch_message(int(pulse.message_id))
                                result = await self.service.resolve_vote(pulse, msg)
                                await ch.send(result["text"])
                            else:
                                await ch.send(f"⌛ **{pulse.label}** expired — the answer was **{pulse.answer}**.")
                        except Exception:
                            pass
                continue
            try:
                if await self._should_fire(gid):
                    ch = await self._pulse_channel(guild)
                    if ch:
                        await self.service.fire(gid, ch)
            except Exception as e:
                logger.warning("Pulse fire failed for %s: %s", gid, e)

    @pulse_loop.before_loop
    async def before_pulse_loop(self):
        await self.bot.wait_until_ready()

    @pulse.command(name="fire", description="[Admin] Fire a pulse immediately")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def pulse_fire(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        if not interaction.guild:
            await interaction.followup.send("Server only.", ephemeral=True)
            return
        if self.service.active_pulse(str(interaction.guild.id)):
            await interaction.followup.send("A pulse is already live.", ephemeral=True)
            return
        ch = await self._pulse_channel(interaction.guild)
        if not ch:
            await interaction.followup.send("No `#pulse` channel found.", ephemeral=True)
            return
        pulse = await self.service.fire(str(interaction.guild.id), ch)
        await interaction.followup.send(
            f"⚡ Fired **{pulse.label}**." if pulse else "Could not fire.", ephemeral=True
        )

    @pulse.command(name="status", description="Is a pulse live, when did the last fire, and is anyone around?")
    async def pulse_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        pulse = self.service.active_pulse(gid)
        secs = await self.service.last_fired_seconds(gid)

        # Surface the audience state: the pulse now refuses to fire into an
        # empty room, and that is invisible unless it says so.
        mins = self._minutes_since_activity(gid)
        window = self.bot.presence.window_minutes
        if mins is None:
            audience = (
                "⌛ No activity seen since the bot last started. The pulse waits for "
                "someone to speak or react before it fires."
            )
        elif mins <= window:
            audience = (
                f"👀 **Audience present** - last activity {int(mins)} min ago, inside the "
                f"{window} min window. A pulse can fire."
            )
        else:
            audience = (
                f"💤 **No audience** - last activity {int(mins)} min ago, outside the "
                f"{window} min window. The pulse is waiting rather than "
                "firing into an empty room."
            )

        if pulse:
            head = f"⚡ Live right now: **{pulse.label}**."
        elif secs is None:
            head = "No pulse has fired yet."
        else:
            head = f"Last pulse was **{int(secs // 60)} min** ago."
        await interaction.followup.send(f"{head}\n\n{audience}", ephemeral=True)
