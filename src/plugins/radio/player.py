"""Per-guild radio playback - voice connection and ffmpeg streaming loop."""

import asyncio
import logging
from collections import deque
from typing import List, Optional

import discord

from src.plugins.radio.domain import Track

logger = logging.getLogger("plugins.radio.player")

FFMPEG_BEFORE_OPTS = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"


class GuildPlayer:
    """Owns the voice client and queue for a single guild."""

    def __init__(self, bot, guild_id: str, announce_callback=None):
        self.bot = bot
        self.guild_id = guild_id
        self.announce_callback = announce_callback
        self.queue: deque = deque()
        self.current: Optional[Track] = None
        self.voice_client: Optional[discord.VoiceClient] = None

    def is_playing(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_playing()

    def is_connected(self) -> bool:
        return self.voice_client is not None and self.voice_client.is_connected()

    async def connect(self, channel: discord.VoiceChannel) -> discord.VoiceClient:
        if not self.is_connected():
            self.voice_client = await channel.connect()
        elif self.voice_client.channel != channel:
            await self.voice_client.move_to(channel)
        return self.voice_client

    async def enqueue(self, track: Track) -> None:
        self.queue.append(track)
        if not self.is_playing():
            await self._play_next()

    async def _play_next(self) -> None:
        if not self.queue or not self.voice_client:
            self.current = None
            return
        self.current = self.queue.popleft()
        source = discord.FFmpegOpusAudio(
            self.current.stream_url,
            before_options=FFMPEG_BEFORE_OPTS,
        )
        self.voice_client.play(source, after=lambda e: self._after_playback(e))

    def _after_playback(self, error: Optional[Exception]) -> None:
        if error:
            logger.warning("Playback error in guild %s: %s", self.guild_id, error)
        try:
            fut = asyncio.run_coroutine_threadsafe(self._on_track_end(error), self.bot.loop)
            fut.result(timeout=30)
        except Exception as e:
            logger.warning("Failed to advance queue in guild %s: %s", self.guild_id, e)

    async def _on_track_end(self, error: Optional[Exception]) -> None:
        if self.queue:
            await self._play_next()
            if self.current and self.announce_callback:
                try:
                    await self.announce_callback(self.guild_id, self.current)
                except Exception as e:
                    logger.warning("Announce callback failed: %s", e)
        else:
            self.current = None

    async def skip(self) -> None:
        if self.voice_client and (self.voice_client.is_playing() or self.voice_client.is_paused()):
            self.voice_client.stop()  # triggers after callback, advancing the queue
        else:
            await self._play_next()

    async def stop(self) -> None:
        self.queue.clear()
        self.current = None
        if self.voice_client:
            try:
                self.voice_client.stop()
            except Exception:
                pass
            await self.voice_client.disconnect(force=False)
        self.voice_client = None

    def upcoming(self) -> List[Track]:
        return list(self.queue)