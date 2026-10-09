"""SQLite persistence for games events, players, votes, and anomalies."""

from datetime import datetime
from typing import List, Optional

from src.infrastructure.database.sqlite import connect

from src.plugins.games.domain import (
    ACTIVE_STATUSES,
    Event,
    Player,
    Vote,
    utcnow,
)


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None


class SQLiteGamesRepository:
    def __init__(self, db_path: str):
        self.db_path = db_path

    # --- Events ---

    async def save_event(self, event: Event) -> None:
        query = """
            INSERT INTO games_events (
                event_id, guild_id, status, pot_amount, current_game_index,
                entry_fee, winner_id, started_at, concluded_at, opened_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                status = excluded.status,
                pot_amount = excluded.pot_amount,
                current_game_index = excluded.current_game_index,
                entry_fee = excluded.entry_fee,
                winner_id = excluded.winner_id,
                started_at = excluded.started_at,
                concluded_at = excluded.concluded_at,
                opened_at = excluded.opened_at
        """
        async with connect(self.db_path) as db:
            await db.execute(
                query,
                (
                    event.event_id,
                    event.guild_id,
                    event.status,
                    event.pot_amount,
                    event.current_game_index,
                    event.entry_fee,
                    event.winner_id,
                    event.started_at.isoformat() if event.started_at else None,
                    event.concluded_at.isoformat() if event.concluded_at else None,
                    event.opened_at.isoformat() if event.opened_at else None,
                ),
            )
            await db.commit()

    async def get_event(self, event_id: str) -> Optional[Event]:
        query = """
            SELECT event_id, guild_id, status, pot_amount, current_game_index,
                   entry_fee, winner_id, started_at, concluded_at, opened_at
            FROM games_events WHERE event_id = ?
        """
        async with connect(self.db_path) as db:
            async with db.execute(query, (event_id,)) as cur:
                row = await cur.fetchone()
                return self._row_to_event(row) if row else None

    async def get_active_event(self, guild_id: str) -> Optional[Event]:
        placeholders = ",".join("?" for _ in ACTIVE_STATUSES)
        query = f"""
            SELECT event_id, guild_id, status, pot_amount, current_game_index,
                   entry_fee, winner_id, started_at, concluded_at, opened_at
            FROM games_events
            WHERE guild_id = ? AND status IN ({placeholders})
            ORDER BY started_at DESC, event_id DESC LIMIT 1
        """
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, *ACTIVE_STATUSES)) as cur:
                row = await cur.fetchone()
                return self._row_to_event(row) if row else None

    async def get_last_event(self, guild_id: str) -> Optional[Event]:
        """Most recent event in any status, used to rate-limit hosted rounds."""
        query = """
            SELECT event_id, guild_id, status, pot_amount, current_game_index,
                   entry_fee, winner_id, started_at, concluded_at, opened_at
            FROM games_events WHERE guild_id = ?
            ORDER BY rowid DESC LIMIT 1
        """
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id,)) as cur:
                row = await cur.fetchone()
                return self._row_to_event(row) if row else None

    @staticmethod
    def _row_to_event(row) -> Event:
        return Event(
            event_id=row[0],
            guild_id=row[1],
            status=row[2],
            pot_amount=row[3],
            current_game_index=row[4],
            entry_fee=row[5],
            winner_id=row[6],
            started_at=_parse_dt(row[7]),
            concluded_at=_parse_dt(row[8]),
            opened_at=_parse_dt(row[9]),
        )

    # --- Players ---

    async def save_player(self, player: Player) -> None:
        query = """
            INSERT INTO games_players (
                guild_id, event_id, user_id, player_number, is_alive,
                survival_streak, elimination_reason, eliminated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, event_id, user_id) DO UPDATE SET
                player_number = excluded.player_number,
                is_alive = excluded.is_alive,
                survival_streak = excluded.survival_streak,
                elimination_reason = excluded.elimination_reason,
                eliminated_at = excluded.eliminated_at
        """
        async with connect(self.db_path) as db:
            await db.execute(
                query,
                (
                    player.guild_id,
                    player.event_id,
                    player.user_id,
                    player.player_number,
                    1 if player.is_alive else 0,
                    player.survival_streak,
                    player.elimination_reason,
                    player.eliminated_at.isoformat() if player.eliminated_at else None,
                ),
            )
            await db.commit()

    async def get_player(self, guild_id: str, event_id: str, user_id: str) -> Optional[Player]:
        query = """
            SELECT guild_id, event_id, user_id, player_number, is_alive,
                   survival_streak, elimination_reason, eliminated_at
            FROM games_players WHERE guild_id = ? AND event_id = ? AND user_id = ?
        """
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, event_id, user_id)) as cur:
                row = await cur.fetchone()
                return self._row_to_player(row) if row else None

    async def list_players(self, guild_id: str, event_id: str, alive_only: bool = False) -> List[Player]:
        query = """
            SELECT guild_id, event_id, user_id, player_number, is_alive,
                   survival_streak, elimination_reason, eliminated_at
            FROM games_players WHERE guild_id = ? AND event_id = ?
        """
        params = [guild_id, event_id]
        if alive_only:
            query += " AND is_alive = 1"
        query += " ORDER BY player_number ASC"
        async with connect(self.db_path) as db:
            async with db.execute(query, params) as cur:
                rows = await cur.fetchall()
                return [self._row_to_player(r) for r in rows]

    async def count_survived(self, guild_id: str, user_id: str) -> int:
        """Events this member was still standing at the end of."""
        async with connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM games_players "
                "WHERE guild_id = ? AND user_id = ? AND is_alive = 1",
                (guild_id, user_id),
            ) as cur:
                row = await cur.fetchone()
                return row[0] if row else 0

    async def get_next_number(self, guild_id: str, event_id: str) -> str:
        async with connect(self.db_path) as db:
            async with db.execute(
                "SELECT player_number FROM games_players WHERE guild_id = ? AND event_id = ?",
                (guild_id, event_id),
            ) as cur:
                rows = await cur.fetchall()
                assigned = {int(r[0]) for r in rows if r[0].isdigit()}
        for n in range(1, 457):
            if n not in assigned:
                return f"{n:03d}"
        return f"{len(assigned) + 1:03d}"

    @staticmethod
    def _row_to_player(row) -> Player:
        return Player(
            guild_id=row[0],
            event_id=row[1],
            user_id=row[2],
            player_number=row[3],
            is_alive=bool(row[4]),
            survival_streak=row[5],
            elimination_reason=row[6],
            eliminated_at=_parse_dt(row[7]),
        )

    # --- Votes ---

    async def record_vote(self, vote: Vote) -> None:
        query = """
            INSERT INTO games_votes (guild_id, event_id, user_id, choice, voted_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, event_id, user_id) DO UPDATE SET
                choice = excluded.choice,
                voted_at = excluded.voted_at
        """
        async with connect(self.db_path) as db:
            await db.execute(
                query,
                (
                    vote.guild_id,
                    vote.event_id,
                    vote.user_id,
                    vote.choice,
                    vote.voted_at.isoformat(),
                ),
            )
            await db.commit()

    async def list_votes(self, guild_id: str, event_id: str) -> List[Vote]:
        query = """
            SELECT guild_id, event_id, user_id, choice, voted_at
            FROM games_votes WHERE guild_id = ? AND event_id = ? ORDER BY voted_at ASC
        """
        async with connect(self.db_path) as db:
            async with db.execute(query, (guild_id, event_id)) as cur:
                rows = await cur.fetchall()
                return [
                    Vote(guild_id=r[0], event_id=r[1], user_id=r[2], choice=r[3], voted_at=_parse_dt(r[4]) or utcnow())
                    for r in rows
                ]

    async def clear_votes(self, guild_id: str, event_id: str) -> None:
        async with connect(self.db_path) as db:
            await db.execute(
                "DELETE FROM games_votes WHERE guild_id = ? AND event_id = ?",
                (guild_id, event_id),
            )
            await db.commit()

    # --- Anomalies ---

    async def record_anomaly(self, guild_id: str, event_id: str, user_id: str, reason: str) -> None:
        query = """
            INSERT INTO games_movement_anomalies (guild_id, event_id, user_id, occurred_at, reason)
            VALUES (?, ?, ?, ?, ?)
        """
        async with connect(self.db_path) as db:
            await db.execute(query, (guild_id, event_id, user_id, utcnow().isoformat(), reason))
            await db.commit()
