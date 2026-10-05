"""Pulse service - the engine that fires, resolves, and pays pulses."""

import logging
from datetime import datetime
from typing import Optional

import discord

from src.plugins.bank.domain import TREASURY
from src.plugins.pulse.domain import (
    PULSE_PRIZE_SPI,
    PULSE_TIMEOUT_SECONDS,
    SNAP_COMPENSATION_SPI,
    SNAP_FINE_SPI,
    SNAP_GUILTY_EMOJI,
    SNAP_INNOCENT_EMOJI,
    ActivePulse,
    utcnow,
)
from src.plugins.pulse.modules import build_random
from src.plugins.pulse.repository import SQLitePulseRepository

logger = logging.getLogger("plugins.pulse.service")


class PulseService:
    def __init__(self, repo: SQLitePulseRepository):
        self.repo = repo
        self.bank = None
        self.community = None
        self.active: dict = {}

    def attach_bank(self, bank) -> None:
        self.bank = bank

    def attach_community(self, community) -> None:
        self.community = community

    def active_pulse(self, guild_id: str) -> Optional[ActivePulse]:
        return self.active.get(guild_id)

    def clear(self, guild_id: str) -> None:
        self.active.pop(guild_id, None)

    async def fire(self, guild_id: str, channel) -> Optional[ActivePulse]:
        if self.active.get(guild_id):
            return None
        spec = await build_random(self.community, guild_id)
        if not spec:
            return None
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
            vote_options=spec.get("vote_options", {}),
            timeout_seconds=spec.get("timeout_seconds", PULSE_TIMEOUT_SECONDS),
            data=spec.get("data", {}),
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

    # --- Vote mode (Snap Trial) ---

    async def resolve_vote(self, pulse: ActivePulse, message: discord.Message) -> dict:
        counts = await self._tally(pulse, message)
        if pulse.kind == "snap_trial":
            return await self._snap_verdict(pulse, counts)
        return {"text": f"⌛ **{pulse.label}** closed.", "verdict": "closed"}

    async def _tally(self, pulse: ActivePulse, message: discord.Message) -> dict:
        accused_id = pulse.data.get("accused_id")
        voter_choices: dict = {}
        for reaction in message.reactions:
            emoji = str(reaction.emoji)
            if emoji not in pulse.vote_options:
                continue
            try:
                async for user in reaction.users():
                    uid = str(user.id)
                    if user.bot or uid == accused_id:
                        continue
                    if self.community and not await self.community.is_citizen(pulse.guild_id, uid):
                        continue
                    voter_choices.setdefault(uid, set()).add(emoji)
            except Exception as e:
                logger.warning("Snap trial tally fetch failed: %s", e)
        counts = {emoji: 0 for emoji in pulse.vote_options}
        for choices in voter_choices.values():
            if len(choices) == 1:  # a voter who clicked both cancels themselves out
                counts[next(iter(choices))] += 1
        return counts

    async def _snap_verdict(self, pulse: ActivePulse, counts: dict) -> dict:
        guilty = counts.get(SNAP_GUILTY_EMOJI, 0)
        innocent = counts.get(SNAP_INNOCENT_EMOJI, 0)
        accused_id = pulse.data.get("accused_id")
        crime = pulse.data.get("crime", "unknown charges")
        tally = f"({guilty}{SNAP_GUILTY_EMOJI} / {innocent}{SNAP_INNOCENT_EMOJI})"

        if guilty + innocent == 0:
            return {
                "verdict": "silent",
                "text": (
                    f"⚖️ **SNAP TRIAL** of <@{accused_id}> for *{crime}* — the collective "
                    f"stayed silent. Case dismissed, no spi moves."
                ),
            }

        if guilty > innocent:
            if self.bank:
                try:
                    await self.bank.transfer(
                        pulse.guild_id, accused_id, TREASURY, SNAP_FINE_SPI, "snap trial fine"
                    )
                    return {
                        "verdict": "guilty",
                        "text": (
                            f"⚖️ **GUILTY** {tally} — <@{accused_id}> pays **{SNAP_FINE_SPI} spi** "
                            f"to the treasury for *{crime}*."
                        ),
                    }
                except Exception:
                    return {
                        "verdict": "guilty_broke",
                        "text": (
                            f"⚖️ **GUILTY** {tally} — but <@{accused_id}> is broke and cannot pay "
                            f"the **{SNAP_FINE_SPI} spi** fine for *{crime}*. Shame on the ledger."
                        ),
                    }
            return {
                "verdict": "guilty",
                "text": f"⚖️ **GUILTY** {tally} — <@{accused_id}> for *{crime}*.",
            }

        # Innocent (or a tie) - the collective compensates the accused
        if self.bank:
            try:
                await self.bank.grant(
                    pulse.guild_id, accused_id, SNAP_COMPENSATION_SPI, "snap trial compensation"
                )
                return {
                    "verdict": "innocent",
                    "text": (
                        f"⚖️ **INNOCENT** {tally} — <@{accused_id}> walks free. The collective "
                        f"pays **{SNAP_COMPENSATION_SPI} spi** for the trouble."
                    ),
                }
            except Exception:
                pass
        return {
            "verdict": "innocent",
            "text": f"⚖️ **INNOCENT** {tally} — <@{accused_id}> walks free for *{crime}*.",
        }
