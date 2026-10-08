"""Glass Bridge runner.

Unlike the Red Light runner this is not a timed light cycle - the bridge is
event-driven. Players click Left/Right (handled by BridgeView, which calls
arena.handle_choice), and this runner's job is the three things a view cannot do:
render and refresh the board, enforce the per-turn timeout, and conclude the
event once everyone has fallen or crossed.

Turn timeout is detected by watching for state change: if the board signature is
unchanged for TURN_TIMEOUT_SECONDS, the current player has stalled and is
eliminated via arena.handle_stall.
"""

import asyncio
import logging
from typing import Callable, Optional

import discord

from src.interface.channel_router import ChannelRouter
from src.plugins.games.bridge_view import BridgeView
from src.plugins.games.formatters import build_bridge_embed

logger = logging.getLogger("plugins.games.bridge_runner")

TURN_TIMEOUT_SECONDS = 30
POLL_SECONDS = 2.0


class GlassBridgeRunner:
    def __init__(self, bot: discord.Client, arena, channel_router: Optional[ChannelRouter] = None):
        self.bot = bot
        self.arena = arena
        self.channel_router = channel_router

    def _signature(self, game, guild_id: str):
        board = game.board(guild_id)
        if not board:
            return None
        return (
            board["current_player"],
            board["current_row"],
            tuple(board["known"]),
            tuple(board["queue"]),
        )

    async def _render(self, board_msg, game, guild_id: str) -> None:
        if not board_msg:
            return
        board = game.board(guild_id)
        if not board:
            return
        try:
            await board_msg.edit(embed=build_bridge_embed(board))
        except Exception:
            pass

    async def run(self, channel, guild_id: str, on_cleanup: Optional[Callable[[str], None]] = None) -> None:
        event = await self.arena.get_active_event(guild_id)
        if not event:
            await channel.send("No active event found.")
            if on_cleanup:
                on_cleanup(guild_id)
            return

        game = await self.arena.current_game(guild_id)
        if not game:
            await channel.send("The bridge is not set up.")
            if on_cleanup:
                on_cleanup(guild_id)
            return

        board_msg = None
        try:
            view = BridgeView(self.arena, self.channel_router)
            board_msg = await channel.send(embed=build_bridge_embed(game.board(guild_id)), view=view)
            try:
                await board_msg.pin()
            except Exception:
                pass
            await channel.send(
                "Cross one at a time. On your turn, choose **Left** or **Right**. "
                f"You have {TURN_TIMEOUT_SECONDS}s per step or the glass gives way."
            )

            loop = asyncio.get_event_loop()
            last_sig = self._signature(game, guild_id)
            turn_started = loop.time()

            while True:
                await asyncio.sleep(POLL_SECONDS)
                state = game.get_state(guild_id)
                if not state or state["done"]:
                    break

                sig = self._signature(game, guild_id)
                now = loop.time()
                if sig != last_sig:
                    # A move happened; reset the turn clock and refresh the board.
                    last_sig = sig
                    turn_started = now
                    await self._render(board_msg, game, guild_id)
                elif now - turn_started >= TURN_TIMEOUT_SECONDS:
                    move = await self.arena.handle_stall(guild_id)
                    if move:
                        try:
                            await channel.send(
                                f"⌛ <@{move.user_id}> did not choose in time. The glass gives way."
                            )
                        except Exception:
                            pass
                    last_sig = self._signature(game, guild_id)
                    turn_started = loop.time()
                    await self._render(board_msg, game, guild_id)

            await self._conclude(channel, guild_id)

        except asyncio.CancelledError:
            logger.info("Glass bridge cancelled for guild %s", guild_id)
            raise
        except Exception as e:
            logger.error("Error in glass bridge session: %s", e, exc_info=True)
            raise
        finally:
            if board_msg:
                try:
                    await board_msg.unpin()
                except Exception:
                    pass
            if on_cleanup:
                on_cleanup(guild_id)

    async def _conclude(self, channel, guild_id: str) -> None:
        result = await self.arena.conclude_event(guild_id)
        if result.winner_id:
            await channel.send(
                f"**WINNER:** <@{result.winner_id}> crossed the bridge and takes the pot of "
                f"**{result.pot_formatted}**."
            )
        elif result.survivor_count > 0:
            await channel.send(
                f"**{result.survivor_count} crossed.** They split **{result.pot_formatted}** "
                f"(~{result.payout_per_survivor:,} spi each)."
            )
        else:
            await channel.send("**Nobody crossed.** The pot carries to the next event.")
