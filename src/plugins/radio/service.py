"""Radio application service - orchestration over resolver, players, and channel:: announcements."""

import logging
from typing import List, Optional

import discord

from src.plugins.radio.domain import NoActivePlayer, Track
from src.plugins.radio.player import GuildPlayer
from src.plugins.radio.resolver import SourceResolver

logger = logging.getLogger("plugins.radio.service")


class RadioService:
    def __init__(self, bot, resolver: SourceResolver, channel_router):
        self.bot = bot
        self.resolver = resolver
        self.channel_router = channel_router
        self._players = {}

    def _player(self, guild_id: str) -> GuildPlayer:
        if guild_id not in self._players:
            self._players[guild_id] = GuildPlayer(self.bot, guild_id, announce_callback=self._announce)
        return self._players[guild_id]

    async def play(self, guild_id: str, voice_channel: discord.VoiceChannel, query: str, requester_id: str) -> Track:
        track = await self.resolver.resolve(query, requester_id)
        player = self._player(guild_id)
        await player.connect(voice_channel)
        await player.enqueue(track)
        return track

    async def skip(self, guild_id: str) -> Track:
        player = self._player(guild_id)
        if not player.is_connected():
            raise NoActivePlayer("The radio is not connected to a voice channel.")
        await player.skip()
        return player.current

    async def stop(self, guild_id: str) -> None:
        player = self._player(guild_id)
        await player.stop()

    def current(self, guild_id: str) -> Optional[Track]:
        return self._player(guild_id).current

    def queue(self, guild_id: str) -> List[Track]:
        return self._player(guild_id).upcoming()

    async def _announce(self, guild_id: str, track: Track) -> None:
        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            return
        ch = await self.channel_router.get(guild, "radio")
        if ch:
            try:
                await ch.send(f"📻 Now playing: **{track.title}** (requested by <@{track.requester_id}>)")
            except Exception as e:
                logger.warning("Could not announce track in guild %s: %s", guild_id, e)