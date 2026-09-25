"""
SQLite implementation of the SquidRepository.

What it does:
- Persists Squid Game players and season aggregates in SQLite.
- Computes sequential player numbers (001-456).

What it does NOT do:
- Does NOT contain business rules or audio synthesis logic.
"""

from typing import Optional, List
from datetime import datetime
import aiosqlite

from src.domain.entities.squid_player import SquidPlayer
from src.domain.entities.squid_season import SquidSeason
from src.domain.entities.movement_anomaly import MovementAnomaly
from src.domain.interfaces.squid_repository import SquidRepository

class SquidSqliteRepository(SquidRepository):
    """Persistence adapter for Squid Game entities using aiosqlite."""

    def __init__(self, db_path: str):
        self.db_path = db_path

    async def save_player(self, player: SquidPlayer) -> None:
        """Upserts a player row."""
        query = """
            INSERT INTO squid_players (
                guild_id, user_id, player_number, is_alive, survival_streak,
                elimination_reason, eliminated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                player_number = excluded.player_number,
                is_alive = excluded.is_alive,
                survival_streak = excluded.survival_streak,
                elimination_reason = excluded.elimination_reason,
                eliminated_at = excluded.eliminated_at
        """
        elim_str = player.eliminated_at.isoformat() if player.eliminated_at else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                query,
                (
                    player.guild_id,
                    player.user_id,
                    player.player_number,
                    1 if player.is_alive else 0,
                    player.survival_streak,
                    player.elimination_reason,
                    elim_str
                )
            )
            await db.commit()

    async def get_player(self, guild_id: str, user_id: str) -> Optional[SquidPlayer]:
        """Loads a player by guild and user ID."""
        query = "SELECT guild_id, user_id, player_number, is_alive, survival_streak, elimination_reason, eliminated_at FROM squid_players WHERE guild_id = ? AND user_id = ?"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, (guild_id, user_id)) as cursor:
                row = await cursor.fetchone()
                return self._row_to_player(row) if row else None

    async def get_player_by_number(self, guild_id: str, player_number: str) -> Optional[SquidPlayer]:
        """Loads a player by their 3-digit tag."""
        query = "SELECT guild_id, user_id, player_number, is_alive, survival_streak, elimination_reason, eliminated_at FROM squid_players WHERE guild_id = ? AND player_number = ?"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, (guild_id, player_number)) as cursor:
                row = await cursor.fetchone()
                return self._row_to_player(row) if row else None

    async def list_players(self, guild_id: str, alive_only: bool = False) -> List[SquidPlayer]:
        """Lists enrolled players ordered by player number."""
        query = "SELECT guild_id, user_id, player_number, is_alive, survival_streak, elimination_reason, eliminated_at FROM squid_players WHERE guild_id = ?"
        params = [guild_id]
        if alive_only:
            query += " AND is_alive = 1"
        query += " ORDER BY player_number ASC"

        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [self._row_to_player(r) for r in rows]

    async def get_next_available_number(self, guild_id: str) -> str:
        """Finds next sequential number from 001 up to 456."""
        query = "SELECT player_number FROM squid_players WHERE guild_id = ?"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, (guild_id,)) as cursor:
                rows = await cursor.fetchall()
                assigned = {int(r[0]) for r in rows if r[0].isdigit()}

        for n in range(1, 457):
            if n not in assigned:
                return f"{n:03d}"
        return f"{len(assigned) + 1:03d}"

    async def save_season(self, season: SquidSeason) -> None:
        """Upserts a season record."""
        query = """
            INSERT INTO squid_seasons (guild_id, pot_amount, is_active, current_game)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                pot_amount = excluded.pot_amount,
                is_active = excluded.is_active,
                current_game = excluded.current_game
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                query,
                (season.guild_id, season.pot_amount, 1 if season.is_active else 0, season.current_game)
            )
            await db.commit()

    async def get_season(self, guild_id: str) -> Optional[SquidSeason]:
        """Loads a season record."""
        query = "SELECT guild_id, pot_amount, is_active, current_game FROM squid_seasons WHERE guild_id = ?"
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(query, (guild_id,)) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return SquidSeason(
                    guild_id=row[0],
                    pot_amount=row[1],
                    is_active=bool(row[2]),
                    current_game=row[3]
                )

    async def record_anomaly(self, anomaly: MovementAnomaly) -> None:
        """Logs a movement violation or close-call event."""
        query = """
            INSERT INTO movement_anomalies (guild_id, user_id, occurred_at, reason)
            VALUES (?, ?, ?, ?)
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                query,
                (anomaly.guild_id, anomaly.user_id, anomaly.occurred_at.isoformat(), anomaly.reason)
            )
            await db.commit()

    async def atomic_eliminate_and_reward(
        self,
        player: SquidPlayer,
        season: SquidSeason
    ) -> None:
        """Atomically persists player elimination and increments season prize pool in an isolated transaction."""
        elim_str = player.eliminated_at.isoformat() if player.eliminated_at else None
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("BEGIN IMMEDIATE")
            try:
                await db.execute(
                    """
                    UPDATE squid_players
                    SET is_alive = ?, survival_streak = ?, elimination_reason = ?, eliminated_at = ?
                    WHERE guild_id = ? AND user_id = ?
                    """,
                    (
                        1 if player.is_alive else 0,
                        player.survival_streak,
                        player.elimination_reason,
                        elim_str,
                        player.guild_id,
                        player.user_id
                    )
                )
                await db.execute(
                    """
                    INSERT INTO squid_seasons (guild_id, pot_amount, is_active, current_game)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(guild_id) DO UPDATE SET
                        pot_amount = excluded.pot_amount,
                        is_active = excluded.is_active,
                        current_game = excluded.current_game
                    """,
                    (season.guild_id, season.pot_amount, 1 if season.is_active else 0, season.current_game)
                )
                await db.commit()
            except Exception:
                await db.rollback()
                raise

    async def revive_all_players(self, guild_id: str) -> int:
        """Revives all eliminated contestants for a new game."""
        query = """
            UPDATE squid_players
            SET is_alive = 1, elimination_reason = NULL, eliminated_at = NULL
            WHERE guild_id = ?
        """
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(query, (guild_id,))
            await db.commit()
            return cursor.rowcount

    async def reset_season(self, guild_id: str) -> None:
        """Resets the prize pot and restores default season configuration."""
        query = """
            INSERT INTO squid_seasons (guild_id, pot_amount, is_active, current_game)
            VALUES (?, 0, 1, 'Red Light Green Light')
            ON CONFLICT(guild_id) DO UPDATE SET
                pot_amount = 0,
                is_active = 1,
                current_game = 'Red Light Green Light'
        """
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(query, (guild_id,))
            await db.commit()

    def _row_to_player(self, row: tuple) -> SquidPlayer:
        elim_at = datetime.fromisoformat(row[6]) if row[6] else None
        return SquidPlayer(
            guild_id=row[0],
            user_id=row[1],
            player_number=row[2],
            is_alive=bool(row[3]),
            survival_streak=row[4],
            elimination_reason=row[5],
            eliminated_at=elim_at
        )
