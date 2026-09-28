"""Pulse service - the engine that fires, resolves, and pays pulses."""

import logging
from datetime import datetime
from typing import Optional

import discord

from src.plugins.pulse.domain import PULSE_PRIZE_SPI, ActivePulse, utcnow
from src.plugins.pulse.modules import build_random
from src.plugins.pulse.repository import SQLitePulseRepository

logger = logging.getLogger("plugins.pulse.service")


class PulseService:
    def __init__(self, repo: SQLitePulseRepository):
        self.repo = repo
        self.bank = None
        self.active: dict = {}

    def attach_bank(self, bank) -> None:
        self.bank = bank

    def active_pulse(self, guild_id: str) -> Optional[ActivePulse]:
        return self.active.get(guild_id)

    def clear(self, guild_id: str) -> None:
        self.active.pop(guild_id, None)

    async def fire(self, guild_id: str, channel) -> Optional[ActivePulse]:
        spec = build_random()
        try:
            msg = await channel.send(
                content="**⚡ THE PULSE** — @everyone",
                embed=spec.get("embed"),
                allowed_mentions=discord.AllowedMentions(everyone=True),
            )
        except Exception as e:
            logger.warning("Could not post pulse: %s", e)
            return None

        for reaction in spec.get("reactions", []):
            try:
                await msg.add_reaction(reaction)
            except Exception:
                pass

        pulse = ActivePulse(
            guild_id=guild_id,
            channel_id=str(channel.id),
            message_id=str(msg.id),
            kind=spec["kind"],
            label=spec["label"],
            answer=spec["answer"],
            mode=spec["mode"],
            started_at=utcnow(),
            accept=tuple(spec.get("accept", [])),
        )
        self.active[guild_id] = pulse
        await self.repo.set_last_fired(guild_id, utcnow().isoformat())
        return pulse

    async def grant(self, guild_id: str, user_id: str, amount: int = PULSE_PRIZE_SPI) -> None:
        if not self.bank:
            return
        try:
            await self.bank.grant(guild_id, user_id, amount, "pulse win")
        except Exception as e:
            logger.warning("Pulse prize grant failed: %s", e)

    async def last_fired_seconds(self, guild_id: str) -> Optional[float]:
        raw = await self.repo.get_last_fired(guild_id)
        if not raw:
            return None
        try:
            return (utcnow() - datetime.fromisoformat(raw)).total_seconds()
        except Exception:
            return None