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
from typing import Optional, Callable
import discord

from src.application.services.squid_service import SquidService
from src.domain.interfaces.audio_deliverer import AudioDeliverer
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer
from src.domain.entities.guard_voice import GuardVoiceLines, GUARD_PROFILE
from src.interface.squid_formatters import build_red_light_embed, build_squid_status_embed
from src.interface.views.move_view import MoveView
from src.interface.channel_router import ChannelRouter

logger = logging.getLogger("interface.red_light_runner")

ALLOWED_MENTIONS = discord.AllowedMentions(users=True, roles=False, everyone=False)

class RedLightRunner:
    """Orchestrates automated game loop, audio cues, state checks, and arena cleanup."""

    def __init__(
        self,
        bot: discord.Client,
        squid_service: SquidService,
        audio_deliverer: AudioDeliverer,
        synthesizer: Optional[SpeechSynthesizer] = None,
        channel_router: Optional[ChannelRouter] = None
    ):
        self.bot = bot
        self.squid_service = squid_service
        self.audio_deliverer = audio_deliverer
        self.synthesizer = synthesizer
        self.channel_router = channel_router

    async def run(
        self,
        channel: discord.abc.Messageable,
        guild_id: str,
        on_cleanup: Optional[Callable[[str], None]] = None
    ) -> None:
        """Executes the complete Red Light Green Light match lifecycle."""
        active_audio_msg: Optional[discord.Message] = None
        track_msg: Optional[discord.Message] = None

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

            living = await self.squid_service.squid_repo.list_players(guild_id, alive_only=True)
            move_view = MoveView(self.squid_service, self.channel_router)
            initial_embed = build_red_light_embed(
                light="GREEN",
                target=100,
                progress={},
                round_num=1,
                max_rounds=5,
                alive_count=len(living)
            )
            track_msg = await channel.send(
                embed=initial_embed,
                view=move_view,
                allowed_mentions=ALLOWED_MENTIONS
            )
            try:
                await track_msg.pin()
            except Exception:
                pass

            if intro_audio:
                await _play_transient_audio(intro_audio, "intro.wav")
            await asyncio.sleep(5.0)

            async def _sleep_with_debounce(duration: float, light: str, round_num: int) -> None:
                loop = asyncio.get_event_loop()
                end_time = loop.time() + duration
                while True:
                    now = loop.time()
                    remaining = end_time - now
                    if remaining <= 0:
                        break
                    step = min(remaining, 1.5)
                    await asyncio.sleep(step)
                    game_state = self.squid_service.get_active_game(guild_id)
                    if game_state and game_state.get("board_dirty"):
                        game_state["board_dirty"] = False
                        embed = await self._build_board_embed(guild_id, light, round_num)
                        try:
                            await track_msg.edit(content=None, embed=embed, allowed_mentions=ALLOWED_MENTIONS)
                        except Exception:
                            pass

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
                green_embed = await self._build_board_embed(guild_id, "GREEN", round_num)
                try:
                    await track_msg.edit(content=None, embed=green_embed, allowed_mentions=ALLOWED_MENTIONS)
                except Exception:
                    pass

                green_audio = (
                    self.squid_service.get_cached_audio("green_korean")
                    or self.squid_service.get_cached_audio("green_english")
                )
                if green_audio:
                    await _play_transient_audio(green_audio, "doll_green.wav")

                chant_duration = max(3.5, 6.5 - (round_num * 0.5)) + random.uniform(-0.3, 0.3)
                await _sleep_with_debounce(chant_duration, "GREEN", round_num)

                active_racers = await self.squid_service.get_active_racers(guild_id)
                if not active_racers:
                    break

                # 2. RED LIGHT
                self.squid_service.set_light(guild_id, "RED", round_num=round_num)
                red_embed = await self._build_board_embed(guild_id, "RED", round_num)
                try:
                    await track_msg.edit(content=None, embed=red_embed, allowed_mentions=ALLOWED_MENTIONS)
                except Exception:
                    pass

                red_audio = self.squid_service.get_cached_audio("red")
                if red_audio:
                    await _play_transient_audio(red_audio, "doll_red.wav")

                red_duration = random.uniform(3.5, 5.0)
                await _sleep_with_debounce(red_duration, "RED", round_num)

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

            await channel.send("🧹 **Session data cleared.** Contestants must use `/squid join` to register for the next match.")

        except asyncio.CancelledError:
            logger.info("Red light automated session cancelled for guild %s", guild_id)
            raise
        except Exception as e:
            logger.error("Error in automated red light session: %s", e, exc_info=True)
            raise
        finally:
            if track_msg:
                try:
                    await track_msg.unpin()
                except Exception:
                    pass
            await self.squid_service.clear_session(guild_id)
            guild = getattr(channel, "guild", None)
            if guild:
                await self._cleanup_guild_roles(guild)
            if on_cleanup:
                try:
                    on_cleanup(guild_id)
                except Exception as err:
                    logger.warning("Error running on_cleanup callback for guild %s: %s", guild_id, err)

    async def _build_board_embed(self, guild_id: str, light: str, round_num: int) -> discord.Embed:
        """Helper to build consistent mobile-first embed with live survivor counts."""
        game = self.squid_service.get_active_game(guild_id)
        target = game.get("target", 100) if game else 100
        progress = game.get("progress", {}) if game else {}
        elims = game.get("eliminated_this_round", []) if game else []
        living = await self.squid_service.squid_repo.list_players(guild_id, alive_only=True)
        return build_red_light_embed(
            light=light,
            target=target,
            progress=progress,
            round_num=round_num,
            max_rounds=5,
            alive_count=len(living),
            eliminated_names=elims
        )

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
