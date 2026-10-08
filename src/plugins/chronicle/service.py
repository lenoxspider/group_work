"""Chronicle service - the state's memory.

Recording is deliberately fire-and-forget and must never raise: a citizen
signing, a verdict landing, or a game concluding should not fail because the
history book could not be written. Posting to #chronicle happens separately, in
the cog's loop, so a failed post is retried rather than lost.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List

from src.plugins.chronicle.repository import SQLiteChronicleRepository

logger = logging.getLogger("plugins.chronicle.service")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ChronicleService:
    def __init__(self, repo: SQLiteChronicleRepository):
        self.repo = repo

    async def record(self, guild_id: str, kind: str, text: str) -> None:
        try:
            await self.repo.add(str(guild_id), kind, text, _now())
        except Exception as e:
            logger.warning("Could not record chronicle entry (%s): %s", kind, e)

    async def recent(self, guild_id: str, limit: int = 10) -> List[dict]:
        return await self.repo.recent(str(guild_id), limit)

    async def counts(self, guild_id: str) -> Dict[str, int]:
        return await self.repo.count_by_kind(str(guild_id))
