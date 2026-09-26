"""Unit tests for Squid Game #game-hub channel confinement."""

import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from src.interface.cogs.squid_cog import SquidCog
from src.interface.cogs.move_command_cog import MoveCommandCog

class TestArenaConfinement(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_service = AsyncMock()
        self.mock_service.get_active_game = MagicMock(return_value=None)
        self.mock_deliverer = AsyncMock()
        self.mock_router = AsyncMock()

        self.squid_cog = SquidCog(
            self.mock_bot,
            self.mock_service,
            self.mock_deliverer,
            channel_router=self.mock_router
        )
        self.move_cog = MoveCommandCog(
            self.mock_bot,
            self.mock_service,
            self.mock_deliverer,
            channel_router=self.mock_router
        )

        self.hub_channel = MagicMock(spec=discord.TextChannel)
        self.hub_channel.id = 11111
        self.hub_channel.mention = "<#11111>"

        self.general_channel = MagicMock(spec=discord.TextChannel)
        self.general_channel.id = 22222
        self.general_channel.mention = "<#22222>"

        self.mock_router.resolve.return_value = self.hub_channel

    def _create_interaction(self, channel_id: int):
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.guild = MagicMock()
        interaction.guild.roles = []
        interaction.guild_id = 99999
        interaction.user = MagicMock(spec=discord.Member)
        interaction.user.id = 12345
        interaction.channel_id = channel_id
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()
        return interaction

    async def test_join_in_wrong_channel_rejected(self):
        interaction = self._create_interaction(channel_id=self.general_channel.id)

        await self.squid_cog.join.callback(self.squid_cog, interaction)

        interaction.response.defer.assert_called_once()
        interaction.followup.send.assert_called_once()
        msg = interaction.followup.send.call_args[0][0]
        self.assertIn("Wrong Arena", msg)
        self.mock_service.enroll_player.assert_not_called()

    async def test_join_in_game_hub_allowed(self):
        interaction = self._create_interaction(channel_id=self.hub_channel.id)
        self.mock_service.get_active_game.return_value = None
        self.mock_service.enroll_player.return_value = MagicMock(display_tag="Player 001", user_id="12345", survival_streak=0)

        await self.squid_cog.join.callback(self.squid_cog, interaction)

        interaction.response.defer.assert_called_once()
        self.mock_service.enroll_player.assert_called_once()

    async def test_move_in_wrong_channel_rejected(self):
        interaction = self._create_interaction(channel_id=self.general_channel.id)

        await self.move_cog.move.callback(self.move_cog, interaction)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        interaction.followup.send.assert_called_once()
        msg = interaction.followup.send.call_args[0][0]
        self.assertIn("Wrong Arena", msg)
        self.mock_service.process_move.assert_not_called()

    async def test_move_in_game_hub_allowed(self):
        interaction = self._create_interaction(channel_id=self.hub_channel.id)
        mock_result = MagicMock(
            survived=True,
            is_finished=False,
            status_code="ok",
            status_message="Step taken",
            advance=10,
            distance=20,
            target=100,
            rank=1,
            total_racers=1,
            player_number="001",
            audio_bytes=None
        )
        self.mock_service.handle_move.return_value = mock_result

        await self.move_cog.move.callback(self.move_cog, interaction)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        self.mock_service.handle_move.assert_called_once_with("99999", "12345")

if __name__ == "__main__":
    unittest.main()
