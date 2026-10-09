"""Reconstruct the collective's history from the ledger it already keeps.

The chronicle only records events from the moment it exists. But the founding,
the laws, the signings, the first Games, the verdicts and the proposals all
already happened and are sitting in the database with real timestamps. This
reads them back so #chronicle opens with the country's actual history rather
than an empty page. Nothing here is invented - every line is sourced from a row
that already exists, and the original date is stamped into the text so an entry
posted today still reads as the day it happened.
"""

import logging
from datetime import datetime
from typing import List, Tuple

from src.infrastructure.database.sqlite import connect

logger = logging.getLogger("plugins.chronicle.history")

# Cap the reconstruction so a long-lived server cannot dump an unbounded wall.
MAX_ENTRIES = 60

_VERDICT = {
    "CONVICTED": "found GUILTY",
    "ACQUITTED": "acquitted",
    "LAPSED": "lapsed for want of a quorum",
}


def _date(iso: str) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return str(iso)[:10]


async def reconstruct(db_path: str, guild_id: str) -> List[Tuple[str, str, str]]:
    """Return (kind, text, created_at) entries in chronological order."""
    entries: List[Tuple[str, str, str]] = []
    async with connect(db_path) as db:
        rows = await db.execute_fetchall(
            "SELECT MIN(joined_at) FROM member_registry WHERE guild_id = ?", (guild_id,)
        )
        founded = rows[0][0] if rows and rows[0][0] else None
        if founded:
            entries.append((
                "founding",
                f"📜 {_date(founded)} · The collective was founded. The first comrades were catalogued.",
                founded,
            ))

        for title, fine, ts in await db.execute_fetchall(
            "SELECT title, fine_amount, created_at FROM laws WHERE guild_id = ? ORDER BY created_at",
            (guild_id,),
        ):
            fine_txt = f" (fine {fine} spi)" if fine else ""
            entries.append(("law_enacted", f"📜 {_date(ts)} · {title} was enacted{fine_txt}.", ts))

        for user_id, ts in await db.execute_fetchall(
            "SELECT user_id, signed_at FROM member_registry "
            "WHERE guild_id = ? AND signed_at IS NOT NULL ORDER BY signed_at",
            (guild_id,),
        ):
            entries.append(("citizen_signed", f"🗳️ {_date(ts)} · <@{user_id}> signed the constitution.", ts))

        for event_id, winner, pot, ts in await db.execute_fetchall(
            "SELECT event_id, winner_id, pot_amount, concluded_at FROM games_events "
            "WHERE guild_id = ? AND concluded_at IS NOT NULL ORDER BY concluded_at",
            (guild_id,),
        ):
            if winner:
                pot_txt = f" and took the pot of {pot:,} spi" if pot else ""
                text = f"🎮 {_date(ts)} · The Games ({event_id}) concluded. <@{winner}> stood alone{pot_txt}."
            else:
                text = f"🎮 {_date(ts)} · The Games ({event_id}) concluded with no sole survivor."
            entries.append(("games_concluded", text, ts))

        for case_id, accused, status, ts in await db.execute_fetchall(
            "SELECT case_id, accused_id, status, resolved_at FROM court_cases "
            "WHERE guild_id = ? AND resolved_at IS NOT NULL ORDER BY resolved_at",
            (guild_id,),
        ):
            label = _VERDICT.get(status, str(status).lower())
            entries.append(("court_verdict", f"⚖️ {_date(ts)} · {case_id}: <@{accused}> {label}.", ts))

        for pid, title, status, ts in await db.execute_fetchall(
            "SELECT proposal_id, title, status, resolved_at FROM proposals "
            "WHERE guild_id = ? AND resolved_at IS NOT NULL ORDER BY resolved_at",
            (guild_id,),
        ):
            verb = "passed" if status == "APPROVED" else "was rejected"
            entries.append(("proposal_concluded", f"🏛️ {_date(ts)} · Proposal {pid} “{title}” {verb}.", ts))

        for user_id, amount, ts in await db.execute_fetchall(
            "SELECT from_user, amount, created_at FROM bank_transactions "
            "WHERE guild_id = ? AND reason = 'snap trial fine' ORDER BY created_at",
            (guild_id,),
        ):
            entries.append((
                "snap_trial",
                f"⚖️ {_date(ts)} · Snap Trial: <@{user_id}> fined {amount} spi to the treasury.",
                ts,
            ))

    entries.sort(key=lambda e: e[2] or "")
    return entries[:MAX_ENTRIES]
