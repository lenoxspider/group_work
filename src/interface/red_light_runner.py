"""
Automated Red Light Green Light match execution runner.

What it does:
- Orchestrates multi-round Red Light Green Light game loop in Discord channels.
- Enforces early conditional termination when no players are left able to play.
- Handles normal completion, slacking player timeouts, metrics summary, and session data cleanup.
- Delivers and auto-cleans transient voice audio cues.

What it does NOT do:
- Does NOT execute direct database SQL or subprocess commands.
- Does NOT implement slash command routing.
"""

import logging
import asyncio
import random
from typing import Optional
import discord

from src.application.services.squid_service import SquidService
from src.domain.interfaces.audio_deliverer import AudioDeliverer
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer
from src.domain.entities.guard_voice import GuardVoiceLines, GUARD_PROFILE
from src.interface.squid_formatters import build_red_light_embed, build_squid_status_embed

logger = logging.getLogger("interface.red_light_runner")

class RedLightRunner:
    """Orchestrates automated game loop, audio cues, state checks, and arena cleanup."""

    def __init__(
        self,
        bot: discord.Client,
        squid_service: SquidService,
        audio_deliverer: AudioDeliverer,
        synthesizer: Optional[SpeechSynthesizer] = None
    ):
        self.bot = bot
        self.squid_service = squid_service
        self.audio_deliverer = audio_deliverer
        self.synthesizer = synthesizer

    async def run(self, channel: discord.abc.Messageable, guild_id: str) -> None:
        """Executes the complete Red Light Green Light match lifecycle."""
        active_audio_msg: Optional[discord.Message] = None

        async def _play_transient_audio(audio_bytes: bytes, filename: str) -> None:
            nonlocal active_audio_msg
            if active_audio_msg:
                try:
                    await active_audio_msg.delete()
                except Exception:
                    pass
            try:
                active_audio_msg = await self.audio_deliverer.deliver(channel, audio_bytes, filename)
                if active_audio_msg:
                    async def _auto_cleanup(target_msg: discord.Message) -> None:
                        await asyncio.sleep(5.0)
                        try:
                            await target_msg.delete()
                        except Exception:
                            pass
                    self.bot.loop.create_task(_auto_cleanup(active_audio_msg))
            except Exception:
                pass

        try:
            self.squid_service.start_red_light_game(guild_id, target=100)
            await self.squid_service.preload_audio_cache()

            intro_audio = self.squid_service.get_cached_audio("intro")
            if not intro_audio and self.synthesizer:
                script = GuardVoiceLines.game_announcement("Red Light Green Light")
                intro_audio = await self.synthesizer.synthesize(script, GUARD_PROFILE)

            track_msg = await channel.send(
                "🎮 **Red Light Green Light starting in 5 seconds!** Listen closely to doll audio cues.",
                embed=build_red_light_embed("GREEN", 100, {}, round_num=1, max_rounds=5)
            )
            if intro_audio:
                await _play_transient_audio(intro_audio, "intro.wav")
            await asyncio.sleep(5.0)

            for round_num in range(1, 6):
                game = self.squid_service.get_active_game(guild_id)
                if not game:
                    break

                # Pre-round check: ensure contestants are still able to play
                active_racers = await self.squid_service.get_active_racers(guild_id)
                if not active_racers:
                    break

                # 1. GREEN LIGHT
                self.squid_service.set_light(guild_id, "GREEN", round_num=round_num)
                green_embed = build_red_light_embed(
                    "GREEN",
                    game.get("target", 100),
                    game.get("progress", {}),
                    round_num=round_num,
                    max_rounds=5
                )
                try:
                    await track_msg.edit(content=None, embed=green_embed)
                    await track_msg.clear_reactions()
                    await track_msg.add_reaction("🔊")
                except Exception:
                    track_msg = await channel.send(embed=green_embed)

                green_audio = (
                    self.squid_service.get_cached_audio("green_korean")
                    or self.squid_service.get_cached_audio("green_english")
                )
                if green_audio:
                    await _play_transient_audio(green_audio, "doll_green.wav")

                chant_duration = max(3.5, 6.5 - (round_num * 0.5)) + random.uniform(-0.3, 0.3)
                await asyncio.sleep(chant_duration)

                # Post-green check: did all active contestants reach 100m?
                active_racers = await self.squid_service.get_active_racers(guild_id)
                if not active_racers:
                    break

                # 2. RED LIGHT
                self.squid_service.set_light(guild_id, "RED", round_num=round_num)
                game = self.squid_service.get_active_game(guild_id)
                red_embed = build_red_light_embed(
                    "RED",
                    game.get("target", 100) if game else 100,
                    game.get("progress", {}) if game else {},
                    round_num=round_num,
                    max_rounds=5
                )
                try:
                    await track_msg.edit(content=None, embed=red_embed)
                    await track_msg.clear_reactions()
                    await track_msg.add_reaction("🚨")
                except Exception:
                    track_msg = await channel.send(embed=red_embed)

                red_audio = self.squid_service.get_cached_audio("red")
                if red_audio:
                    await _play_transient_audio(red_audio, "doll_red.wav")

                red_duration = random.uniform(3.5, 5.0)
                await asyncio.sleep(red_duration)

                # Post-red check: were remaining contestants eliminated?
                active_racers = await self.squid_service.get_active_racers(guild_id)
                if not active_racers:
                    break

            # Match Resolution
            guild = getattr(channel, "guild", None)
            active_racers = await self.squid_service.get_active_racers(guild_id)
            if not active_racers:
                alive_players = await self.squid_service.squid_repo.list_players(guild_id, alive_only=True)
                if not alive_players:
                    await channel.send("💀 **SQUID GAME • TOTAL EXTINCTION**\n*All contestants on the field have been eliminated. Zero survivors.*")
                else:
                    await channel.send("🏆 **ALL CONTESTANTS HAVE COMPLETED THE COURSE!**\n*Every active player reached 100m safely. Match concluded early.*")
            else:
                # Ended normally after 5 rounds: timeout slacking players who failed to reach 100m
                timeout_elims = await self.squid_service.timeout_slacking_players(guild_id)
                if timeout_elims:
                    if guild:
                        for e in timeout_elims:
                            await self._swap_to_spectator(guild, e.user_id)
                    names = ", ".join(f"<@{e.user_id}>" for e in timeout_elims)
                    await channel.send(f"⏰ **TIME EXPIRED!** Eliminated for failing to reach 100m:\n{names}")

            # Present final session metrics before wiping roster
            final_status = await self.squid_service.get_status(guild_id)
            summary_embed = build_squid_status_embed(final_status)
            await channel.send("🏁 **Session completed!** Final arena metrics:", embed=summary_embed)

            # Clear session state and reset roles for next game
            await self.squid_service.clear_session(guild_id)
            if guild:
                await self._cleanup_guild_roles(guild)

            await channel.send("🧹 **Session data cleared.** Contestants must use `/squid join` to register for the next match.")

        except asyncio.CancelledError:
            logger.info("Red light automated session cancelled for guild %s", guild_id)
            await self.squid_service.clear_session(guild_id)
        except Exception as e:
            logger.error("Error in automated red light session: %s", e, exc_info=True)
            await self.squid_service.clear_session(guild_id)

    async def _swap_to_spectator(self, guild: discord.Guild, user_id: str) -> None:
        """Atomically demotes eliminated member to Spectator."""
        try:
            member = guild.get_member(int(user_id))
            if not member:
                return
            p_role = discord.utils.get(guild.roles, name="Player")
            s_role = discord.utils.get(guild.roles, name="Spectator")
            if p_role and p_role in member.roles:
                await member.remove_roles(p_role, reason="Eliminated in Squid Game")
            if s_role and s_role not in member.roles:
                await member.add_roles(s_role, reason="Moved to Spectator deck")
        except Exception as e:
            logger.warning("Failed swapping to spectator for %s: %s", user_id, e)

    async def _cleanup_guild_roles(self, guild: discord.Guild) -> None:
        """Removes temporary Player and Spectator roles on session completion."""
        try:
            p_role = discord.utils.get(guild.roles, name="Player")
            s_role = discord.utils.get(guild.roles, name="Spectator")
            for member in guild.members:
                roles_to_remove = []
                if p_role and p_role in member.roles:
                    roles_to_remove.append(p_role)
                if s_role and s_role in member.roles:
                    roles_to_remove.append(s_role)
                if roles_to_remove:
                    try:
                        await member.remove_roles(*roles_to_remove, reason="Squid Game session reset")
                    except Exception:
                        pass
        except Exception as e:
            logger.warning("Failed cleaning up roles after session: %s", e)
