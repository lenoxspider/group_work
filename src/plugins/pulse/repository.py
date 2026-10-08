"""SQLite persistence for pulse pacing state and the live pulse.

The live pulse is persisted so a restart cannot orphan it: an in-memory-only
pulse lost its judge on reboot, leaving the message sitting in #pulse with no
verdict ever rendered - and for a Snap Trial that meant no fine and no
compensation, with votes already cast against it.

Recovery is cheap because the tally reads reaction state live from the Discord
message, so votes cast while the bot was down are not lost.
"""

import json
from datetime import datetime
from typing import List, Optional

from src.infrastructure.database.sqlite import connect
from src.plugins.pulse.domain import ActivePulse

_ACTIVE_COLS = (
    "guild_id, channel_id, message_id, kind, label, answer, mode, started_at, "
    "accept, vote_options, timeout_seconds, data"
)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _loads(raw: Optional[str], fallback):
    try:
        return json.loads(raw) if raw else fallback
    except (TypeError, ValueError):
        return fallback


class SQLitePulseRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # --- Pacing ---

    async def get_last_fired(self, guild_id: str) -> Optional[str]:
        async with connect(self.db_path) as db:
            async with db.execute(
                "SELECT last_fired FROM pulse_state WHERE guild_id = ?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else None

    async def set_last_fired(self, guild_id: str, ts: str) -> None:
        async with connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO pulse_state (guild_id, last_fired) VALUES (?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET last_fired = excluded.last_fired",
                (guild_id, ts),
            )
            await db.commit()

    # --- The live pulse ---

    async def save_active(self, pulse: ActivePulse) -> None:
        async with connect(self.db_path) as db:
            await db.execute(
                f"INSERT INTO pulse_active ({_ACTIVE_COLS}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(guild_id) DO UPDATE SET "
                "channel_id = excluded.channel_id, "
                "message_id = excluded.message_id, "
                "kind = excluded.kind, "
                "label = excluded.label, "
                "answer = excluded.answer, "
                "mode = excluded.mode, "
                "started_at = excluded.started_at, "
                "accept = excluded.accept, "
                "vote_options = excluded.vote_options, "
                "timeout_seconds = excluded.timeout_seconds, "
                "data = excluded.data",
                (
                    pulse.guild_id,
                    pulse.channel_id,
                    pulse.message_id,
                    pulse.kind,
                    pulse.label,
                    pulse.answer,
                    pulse.mode,
                    pulse.started_at.isoformat(),
                    json.dumps(list(pulse.accept)),
                    json.dumps(pulse.vote_options),
                    pulse.timeout_seconds,
                    json.dumps(pulse.data),
                ),
            )
            await db.commit()

    async def get_active(self, guild_id: str) -> Optional[ActivePulse]:
        async with connect(self.db_path) as db:
            async with db.execute(
                f"SELECT {_ACTIVE_COLS} FROM pulse_active WHERE guild_id = ?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
                return self._row_to_active(row) if row else None

    async def list_active(self) -> List[ActivePulse]:
        async with connect(self.db_path) as db:
            async with db.execute(f"SELECT {_ACTIVE_COLS} FROM pulse_active") as cur:
                rows = await cur.fetchall()
        restored = [self._row_to_active(row) for row in rows]
        return [pulse for pulse in restored if pulse is not None]

    async def clear_active(self, guild_id: str) -> None:
        async with connect(self.db_path) as db:
            await db.execute("DELETE FROM pulse_active WHERE guild_id = ?", (guild_id,))
            await db.commit()

    @staticmethod
    def _row_to_active(row) -> Optional[ActivePulse]:
        """Rebuild a pulse, or None if the row is too corrupt to trust.

        A corrupt row is dropped rather than raised over: one unreadable pulse
        should not stop the plugin from booting.
        """
        started_at = _parse_dt(row[7])
        if not started_at:
            return None
        return ActivePulse(
            guild_id=row[0],
            channel_id=row[1],
            message_id=row[2],
            kind=row[3],
            label=row[4],
            answer=row[5] or "",
            mode=row[6],
            started_at=started_at,
            accept=tuple(_loads(row[8], [])),
            vote_options=_loads(row[9], {}),
            timeout_seconds=row[10],
            data=_loads(row[11], {}),
        )
