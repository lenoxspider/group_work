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

    async def reconstruct_history(self, guild_id: str) -> int:
        """Backfill the chronicle from the ledger the server already keeps.

        Idempotent: if the guild already has entries it does nothing, so running
        it twice cannot duplicate history. Returns the number of entries added.
        """
        gid = str(guild_id)
        if await self.repo.count_entries(gid):
            return 0
        from src.plugins.chronicle.history import reconstruct
        try:
            rows = await reconstruct(self.repo.db_path, gid)
        except Exception as e:
            logger.warning("Chronicle reconstruction failed: %s", e)
            return 0
        for kind, text, created_at in rows:
            await self.repo.add(gid, kind, text, created_at)
        logger.info("Reconstructed %s chronicle entries for %s", len(rows), gid)
        return len(rows)
