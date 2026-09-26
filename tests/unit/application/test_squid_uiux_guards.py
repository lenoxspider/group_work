"""
Unit test suite verifying Squid Game UI/UX guard order and deterministic match lifecycle.
"""

import unittest
import random
from typing import Optional, List
from src.domain.entities.squid_player import SquidPlayer
from src.domain.entities.squid_season import SquidSeason
from src.domain.entities.movement_anomaly import MovementAnomaly
from src.domain.interfaces.squid_repository import SquidRepository
from src.domain.errors import ValidationError
from src.application.services.squid_service import SquidService
from src.interface.squid_formatters import (
    render_progress_bar,
    build_red_light_embed,
    build_ephemeral_move_feedback
)

class InMemorySquidRepository(SquidRepository):
    """Fully in-memory repository for zero-dependency unit tests."""

    def __init__(self):
        self.players: dict[tuple[str, str], SquidPlayer] = {}
        self.seasons: dict[str, SquidSeason] = {}
        self.anomalies: List[MovementAnomaly] = []

    async def get_player(self, guild_id: str, user_id: str) -> Optional[SquidPlayer]:
        return self.players.get((guild_id, user_id))

    async def get_player_by_number(self, guild_id: str, player_number: str) -> Optional[SquidPlayer]:
        for p in self.players.values():
            if p.guild_id == guild_id and p.player_number == player_number:
                return p
        return None

    async def save_player(self, player: SquidPlayer) -> None:
        self.players[(player.guild_id, player.user_id)] = player

    async def list_players(self, guild_id: str, alive_only: bool = False) -> List[SquidPlayer]:
        res = [p for p in self.players.values() if p.guild_id == guild_id]
        if alive_only:
            res = [p for p in res if p.is_alive]
        return res

    async def get_season(self, guild_id: str) -> Optional[SquidSeason]:
        return self.seasons.get(guild_id)

    async def save_season(self, season: SquidSeason) -> None:
        self.seasons[season.guild_id] = season

    async def atomic_eliminate_and_reward(self, player: SquidPlayer, season: SquidSeason) -> None:
        self.players[(player.guild_id, player.user_id)] = player
        self.seasons[season.guild_id] = season

    async def record_anomaly(self, anomaly: MovementAnomaly) -> None:
        self.anomalies.append(anomaly)

    async def clear_players(self, guild_id: str) -> None:
        self.players = {k: v for k, v in self.players.items() if k[0] != guild_id}

    async def get_next_available_number(self, guild_id: str) -> str:
        count = len([p for p in self.players.values() if p.guild_id == guild_id])
        return f"{count + 1:03d}"

    async def revive_all_players(self, guild_id: str) -> int:
        revived = 0
        for p in self.players.values():
            if p.guild_id == guild_id and not p.is_alive:
                p.revive()
                revived += 1
        return revived

    async def reset_season(self, guild_id: str) -> None:
        if guild_id in self.seasons:
            self.seasons[guild_id].reset()


class TestSquidUIUXGuards(unittest.IsolatedAsyncioTestCase):
    """Verifies all Phase 1.5 guards and Phase 5 requirements."""

    def setUp(self):
        self.repo = InMemorySquidRepository()
        self.current_time = 1000.0
        self.fake_clock = lambda: self.current_time
        # Deterministic RNG: seed 42
        self.fake_rng = random.Random(42)
        self.service = SquidService(
            squid_repo=self.repo,
            synthesizer=None,
            clock=self.fake_clock,
            rng=self.fake_rng
        )
        self.guild_id = "test_guild"

    async def _setup_players(self) -> tuple[SquidPlayer, SquidPlayer, SquidPlayer]:
        p1 = SquidPlayer(guild_id=self.guild_id, user_id="u1", player_number="001")
        p2 = SquidPlayer(guild_id=self.guild_id, user_id="u2", player_number="002")
        p3 = SquidPlayer(guild_id=self.guild_id, user_id="u3", player_number="003")
        await self.repo.save_player(p1)
        await self.repo.save_player(p2)
        await self.repo.save_player(p3)
        return p1, p2, p3

    # Guard 2: Reject if not enrolled
    async def test_guard_not_enrolled(self):
        self.service.start_red_light_game(self.guild_id, target=100)
        with self.assertRaises(ValidationError) as ctx:
            await self.service.handle_move(self.guild_id, "ghost_user")
        self.assertIn("not enrolled", str(ctx.exception).lower())

    # Guard 3: Reject if dead
    async def test_guard_dead_player(self):
        p, _, _ = await self._setup_players()
        p.eliminate("Failed earlier round")
        await self.repo.save_player(p)

        self.service.start_red_light_game(self.guild_id, target=100)
        with self.assertRaises(ValidationError) as ctx:
            await self.service.handle_move(self.guild_id, "u1")
        self.assertIn("eliminated and cannot move", str(ctx.exception))

    # Guard 4: Reject if already finished
    async def test_guard_finished_player(self):
        p, _, _ = await self._setup_players()
        self.service.start_red_light_game(self.guild_id, target=100)
        game = self.service.get_active_game(self.guild_id)
        game["finished"].add("u1")

        res = await self.service.handle_move(self.guild_id, "u1")
        self.assertEqual(res.status_code, "finished")
        self.assertTrue(res.is_finished)
        self.assertTrue(res.survived)
        self.assertIn("crossed the finish line", res.status_message)

    # Guard 5: Rate-limit double-tap (per-user, ~0.5s window)
    async def test_guard_double_tap(self):
        await self._setup_players()
        self.service.start_red_light_game(self.guild_id, target=100)
        self.service.set_light(self.guild_id, "GREEN")

        # First tap at t=1000.0
        res1 = await self.service.handle_move(self.guild_id, "u1")
        self.assertEqual(res1.status_code, "ok")
        dist_after_tap1 = res1.distance

        # Double-tap 0.2s later at t=1000.2
        self.current_time = 1000.2
        res2 = await self.service.handle_move(self.guild_id, "u1")
        self.assertEqual(res2.status_code, "double_tap")
        self.assertTrue(res2.is_rate_limited)
        # Distance did NOT increase
        self.assertEqual(res2.distance, dist_after_tap1)

        # Subsequent tap after rate-limit window expires (t=1000.8, 0.6s later)
        self.current_time = 1000.8
        res3 = await self.service.handle_move(self.guild_id, "u1")
        self.assertEqual(res3.status_code, "ok")
        self.assertGreater(res3.distance, dist_after_tap1)

    # Guard 6: Red-phase tap triggers elimination after latency grace
    async def test_guard_red_phase_tap(self):
        await self._setup_players()
        self.service.start_red_light_game(self.guild_id, target=100)
        self.service.set_light(self.guild_id, "RED")

        # Move 1.5s after red light turned on (past 0.5s grace window)
        self.current_time = 1001.5
        res = await self.service.handle_move(self.guild_id, "u1")
        self.assertFalse(res.survived)
        self.assertEqual(res.status_code, "eliminated")

        # Confirm player is eliminated in repository
        p = await self.repo.get_player(self.guild_id, "u1")
        self.assertFalse(p.is_alive)

    # End-to-end match with 3 players: 1 finishes, 1 dies, 1 survives
    async def test_end_to_end_three_players(self):
        p1, p2, p3 = await self._setup_players()
        self.service.start_red_light_game(self.guild_id, target=50)

        # Round 1: GREEN
        self.service.set_light(self.guild_id, "GREEN", round_num=1)
        # P1 safe step + sprint
        res_p1_1 = await self.service.handle_move(self.guild_id, "u1")
        self.current_time += 1.0
        res_p1_2 = await self.service.handle_move(self.guild_id, "u1")
        self.assertTrue(res_p1_1.survived)
        self.assertTrue(res_p1_2.survived)

        # P2 safe step only
        res_p2_1 = await self.service.handle_move(self.guild_id, "u2")
        self.assertTrue(res_p2_1.survived)

        # P3 safe step only
        res_p3_1 = await self.service.handle_move(self.guild_id, "u3")
        self.assertTrue(res_p3_1.survived)

        # Round 1: RED
        self.current_time += 2.0
        self.service.set_light(self.guild_id, "RED", round_num=1)

        # P1 and P2 freeze (no movement)
        # P3 moves during RED at t+1.5s
        self.current_time += 1.5
        res_p3_red = await self.service.handle_move(self.guild_id, "u3")
        self.assertFalse(res_p3_red.survived)
        self.assertEqual(res_p3_red.status_code, "eliminated")

        # Round 2: GREEN
        self.current_time += 3.0
        self.service.set_light(self.guild_id, "GREEN", round_num=2)

        # P1 safe step + sprint crosses 50m target
        res_p1_3 = await self.service.handle_move(self.guild_id, "u1")
        self.current_time += 1.0
        res_p1_4 = await self.service.handle_move(self.guild_id, "u1")
        self.assertTrue(res_p1_4.is_finished)

        # P2 safe step
        res_p2_2 = await self.service.handle_move(self.guild_id, "u2")
        self.assertFalse(res_p2_2.is_finished)
        self.assertTrue(res_p2_2.survived)

        # Verification:
        # P1 finished
        game = self.service.get_active_game(self.guild_id)
        self.assertIn("u1", game["finished"])

        # P3 is dead
        p3_db = await self.repo.get_player(self.guild_id, "u3")
        self.assertFalse(p3_db.is_alive)

        # P2 is alive, survived, not finished
        p2_db = await self.repo.get_player(self.guild_id, "u2")
        self.assertTrue(p2_db.is_alive)
        self.assertNotIn("u2", game["finished"])

    # UI/UX Formatter verification (Phase 2 & 3)
    def test_mobile_first_formatters(self):
        # Monospace progress bar in backticks (2.2)
        bar = render_progress_bar(68, 100, length=10)
        self.assertTrue(bar.startswith("`███████░░░`"))
        self.assertIn("68m / 100m", bar)

        # Green embed footer and layout (2.1 & 2.2)
        green_embed = build_red_light_embed(
            light="GREEN",
            target=100,
            progress={"u1": 68, "u2": 45},
            round_num=3,
            max_rounds=5,
            alive_count=2,
            viewer_id="u1"
        )
        self.assertEqual(green_embed.title, "🟢 GREEN LIGHT — Round 3/5")
        self.assertEqual(green_embed.footer.text, "🟢 ends ~5s · tap MOVE")
        self.assertIn("← you", green_embed.description)

        # Red embed footer and elimination field (2.1 & 2.3)
        red_embed = build_red_light_embed(
            light="RED",
            target=100,
            progress={"u1": 68, "u2": 45},
            round_num=3,
            max_rounds=5,
            alive_count=2,
            eliminated_names=["u3"]
        )
        self.assertEqual(red_embed.title, "🔴 RED LIGHT — Round 3/5")
        self.assertEqual(red_embed.footer.text, "🔴 tap MOVE = eliminated")
        self.assertIn("FREEZE. Tapping MOVE now eliminates you.", red_embed.description)
        field = red_embed.fields[0]
        self.assertEqual(field.name, "💀 Eliminated this round")
        self.assertIn("<@u3>", field.value)

        # 3-line ephemeral reply (3.1)
        from src.application.dtos.squid_dtos import RedLightMoveResultDTO
        dto = RedLightMoveResultDTO(
            guild_id="g",
            user_id="u1",
            player_number="001",
            survived=True,
            distance=68,
            is_finished=False,
            advance=22,
            target=100,
            rank=2,
            total_racers=5,
            status_message="ok"
        )
        feedback = build_ephemeral_move_feedback(dto)
        lines = feedback.splitlines()
        self.assertEqual(len(lines), 3)
        self.assertIn("+22m → 68m/100m", lines[0])
        self.assertTrue(lines[1].startswith("`███████░░░`"))
        self.assertIn("2nd of 5 still running · +32m to finish", lines[2])
