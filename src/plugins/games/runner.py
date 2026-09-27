"""Automated Red Light Green Light match runner.

Drives the arena's round-1 game loop: green/red cycling, audio cues, board
updates, timeout elimination, then concludes the event (payout) and cleans up.
"""

import asyncio
import logging
import random
from typing import Callable, Optional

import discord

from src.domain.interfaces.audio_deliverer import AudioDeliverer
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer
from src.interface.channel_router import ChannelRouter
from src.plugins.games.formatters import build_red_light_embed, build_status_embed
from src.plugins.games.move_view import MoveView
from src.plugins.games.service import ArenaService

logger = logging.getLogger("plugins.games.runner")

ALLOWED_MENTIONS = discord.AllowedMentions(users=True, roles=False, everyone=False)


class RedLightRunner:
    def __init__(
        self,
        bot: discord.Client,
        arena: ArenaService,
        audio_deliverer: AudioDeliverer,
        synthesizer: Optional[SpeechSynthesizer] = None,
        channel_router: Optional[ChannelRouter] = None,
    ):
        self.bot = bot
        self.arena = arena
        self.audio_deliverer = audio_deliverer
        self.synthesizer = synthesizer
        self.channel_router = channel_router

    async def run(self, channel, guild_id: str, on_cleanup: Optional[Callable[[str], None]] = None) -> None:
        event = await self.arena.get_active_event(guild_id)
        if not event:
            await channel.send("No active event found.")
            return

        track_msg: Optional[discord.Message] = None
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
            await self.arena.preload_audio_cache()

            intro_audio = self.arena.get_cached_audio("intro")
            if not intro_audio and self.synthesizer:
                from src.plugins.games.domain import GuardVoiceLines, GUARD_PROFILE
                intro_audio = await self.synthesizer.synthesize(
                    GuardVoiceLines.game_announcement("Red Light Green Light"), GUARD_PROFILE
                )

            living = await self.arena.repo.list_players(guild_id, event.event_id, alive_only=True)
            move_view = MoveView(self.arena, self.channel_router)
            initial_embed = build_red_light_embed(light="GREEN", target=100, progress={}, round_num=1, max_rounds=5, alive_count=len(living))
            track_msg = await channel.send(embed=initial_embed, view=move_view, allowed_mentions=ALLOWED_MENTIONS)
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
                    remaining = end_time - loop.time()
                    if remaining <= 0:
                        break
                    step = min(remaining, 1.5)
                    await asyncio.sleep(step)
                    game_state = self.arena.get_active_game(guild_id)
                    if game_state and game_state.get("board_dirty"):
                        game_state["board_dirty"] = False
                        embed = await self._build_board_embed(guild_id, event.event_id, light, round_num)
                        try:
                            await track_msg.edit(content=None, embed=embed, allowed_mentions=ALLOWED_MENTIONS)
                        except Exception:
                            pass

            for round_num in range(1, 6):
                if not self.arena.get_active_game(guild_id):
                    break

                active_racers = await self.arena.get_active_racers(guild_id)
                if not active_racers:
                    break

                self.arena.set_light(guild_id, "GREEN", round_num=round_num)
                green_embed = await self._build_board_embed(guild_id, event.event_id, "GREEN", round_num)
                try:
                    await track_msg.edit(content=None, embed=green_embed, allowed_mentions=ALLOWED_MENTIONS)
                except Exception:
                    pass

                green_audio = self.arena.get_cached_audio("green_korean") or self.arena.get_cached_audio("green_english")
                if green_audio:
                    await _play_transient_audio(green_audio, "doll_green.wav")

                chant_duration = max(3.5, 6.5 - (round_num * 0.5)) + random.uniform(-0.3, 0.3)
                await _sleep_with_debounce(chant_duration, "GREEN", round_num)

                active_racers = await self.arena.get_active_racers(guild_id)
                if not active_racers:
                    break

                self.arena.set_light(guild_id, "RED", round_num=round_num)
                red_embed = await self._build_board_embed(guild_id, event.event_id, "RED", round_num)
                try:
                    await track_msg.edit(content=None, embed=red_embed, allowed_mentions=ALLOWED_MENTIONS)
                except Exception:
                    pass

                red_audio = self.arena.get_cached_audio("red")
                if red_audio:
                    await _play_transient_audio(red_audio, "doll_red.wav")

                await _sleep_with_debounce(random.uniform(3.5, 5.0), "RED", round_num)

                active_racers = await self.arena.get_active_racers(guild_id)
                if not active_racers:
                    break

            # Match resolution
            guild = getattr(channel, "guild", None)
            active_racers = await self.arena.get_active_racers(guild_id)
            if active_racers:
                timeout_elims = await self.arena.timeout_slacking_players(guild_id)
                if timeout_elims and guild:
                    for e in timeout_elims:
                        await self._swap_to_spectator(guild, e.user_id)
                    names = ", ".join(f"<@{e.user_id}>" for e in timeout_elims)
                    await channel.send(f"**TIME EXPIRED!** Eliminated for failing to reach 100m:\n{names}")

            # Conclude: payout survivors or carry the pot on total extinction.
            result = await self.arena.conclude_event(guild_id)
            if result.winner_id:
                await channel.send(f"**WINNER:** <@{result.winner_id}> takes the pot of **{result.pot_formatted}**.")
            elif result.survivor_count > 0:
                await channel.send(
                    f"**EVENT CONCLUDED.** {result.survivor_count} survivor(s) split **{result.pot_formatted}** "
                    f"(~{result.payout_per_survivor:,} spi each)."
                )
            else:
                await channel.send("**TOTAL EXTINCTION.** No survivors - the pot carries to the next event.")

        except asyncio.CancelledError:
            logger.info("Red Light Green Light session cancelled for guild %s", guild_id)
            raise
        except Exception as e:
            logger.error("Error in red light session: %s", e, exc_info=True)
            raise
        finally:
            if track_msg:
                try:
                    await track_msg.unpin()
                except Exception:
                    pass
            await self.arena.clear_session(guild_id)
            guild = getattr(channel, "guild", None)
            if guild:
                await self._cleanup_guild_roles(guild)
            if on_cleanup:
                try:
                    on_cleanup(guild_id)
                except Exception as err:
                    logger.warning("Error running on_cleanup for guild %s: %s", guild_id, err)

    async def _build_board_embed(self, guild_id: str, event_id: str, light: str, round_num: int) -> discord.Embed:
        game = self.arena.get_active_game(guild_id)
        target = game.get("target", 100) if game else 100
        progress = game.get("progress", {}) if game else {}
        elims = game.get("eliminated_this_round", []) if game else []
        living = await self.arena.repo.list_players(guild_id, event_id, alive_only=True)
        return build_red_light_embed(
            light=light,
            target=target,
            progress=progress,
            round_num=round_num,
            max_rounds=5,
            alive_count=len(living),
            eliminated_names=elims,
        )

    async def _swap_to_spectator(self, guild: discord.Guild, user_id: str) -> None:
        try:
            member = guild.get_member(int(user_id))
            if not member:
                return
            p_role = discord.utils.get(guild.roles, name="Player")
            s_role = discord.utils.get(guild.roles, name="Spectator")
            if p_role and p_role in member.roles:
                await member.remove_roles(p_role, reason="Eliminated in the games")
            if s_role and s_role not in member.roles:
                await member.add_roles(s_role, reason="Moved to Spectator deck")
        except Exception:
            pass

    async def _cleanup_guild_roles(self, guild: discord.Guild) -> None:
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
                        await member.remove_roles(*roles_to_remove, reason="Games session reset")
                    except Exception:
                        pass
        except Exception:
            pass