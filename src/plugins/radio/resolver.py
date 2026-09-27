"""Source resolver - turns a YouTube URL or search query into a streamable Track."""

import asyncio
import logging
import re

from src.plugins.radio.domain import ResolutionError, Track

logger = logging.getLogger("plugins.radio.resolver")


class SourceResolver:
    """Resolves URLs and search queries to direct audio stream URLs via yt-dlp."""

    def _normalize_query(self, query: str) -> str:
        if re.match(r"https?://", query):
            return query
        return f"ytsearch1:{query}"

    def _extract(self, query: str) -> dict:
        import os

        import yt_dlp

        opts = {
            "format": "bestaudio/best",
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
            "extract_flat": False,
            "socket_timeout": 30,
            "retries": 3,
            "extractor_retries": 3,
        }
        # YouTube bot-checks datacenter IPs; log-in cookies bypass it.
        cookies = os.getenv("YTDLP_COOKIES", "").strip()
        if cookies and os.path.exists(cookies):
            opts["cookiefile"] = cookies
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)

        if info is None:
            raise ResolutionError("No results found.")
        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            if not entries:
                raise ResolutionError("No results found.")
            info = entries[0]
        return info

    def _stream_url(self, info: dict) -> str:
        if info.get("url"):
            return info["url"]
        formats = info.get("formats") or []
        audio = [f for f in formats if f.get("acodec") and f.get("acodec") != "none"]
        candidates = audio or formats
        for f in candidates:
            if f.get("url"):
                return f["url"]
        raise ResolutionError("Could not resolve an audio stream for that link.")

    async def resolve(self, query: str, requester_id: str) -> Track:
        """Resolve query in a worker thread (yt-dlp is blocking) into a Track."""
        normalized = self._normalize_query(query)
        try:
            info = await asyncio.to_thread(self._extract, normalized)
        except ResolutionError:
            raise
        except Exception as e:
            logger.warning("yt-dlp extraction failed for %r: %s", query, e)
            raise ResolutionError(f"Could not resolve that link: {e}") from e

        title = info.get("title") or "Untitled"
        duration = int(info.get("duration") or 0)
        stream_url = self._stream_url(info)
        webpage_url = info.get("webpage_url") or query

        return Track(
            url=normalized,
            title=title,
            duration=duration,
            requester_id=requester_id,
            stream_url=stream_url,
            webpage_url=webpage_url,
        )