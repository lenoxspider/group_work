"""Unit tests for CleanupCog commands."""

import unittest
from unittest.mock import AsyncMock, MagicMock
import discord

from src.interface.cogs.cleanup_cog import CleanupCog

class TestCleanupCog(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.mock_bot = MagicMock()
        self.mock_bot.user.id = 99999
        self.mock_router = AsyncMock()
        self.cog = CleanupCog(self.mock_bot, self.mock_router)

    def _create_mock_interaction(self):
        interaction = AsyncMock(spec=discord.Interaction)
        interaction.response = AsyncMock()
        interaction.response.defer = AsyncMock()
        interaction.followup = AsyncMock()
        interaction.followup.send = AsyncMock()
        return interaction

    async def test_cleanup_current_channel_success(self):
        interaction = self._create_mock_interaction()
        channel = MagicMock(spec=discord.TextChannel)
        channel.mention = "#general"
        channel.guild.me = MagicMock()
        channel.permissions_for.return_value.manage_messages = True
        channel.purge = AsyncMock(return_value=[MagicMock(), MagicMock(), MagicMock()])
        interaction.channel = channel

        await self.cog.cleanup.callback(self.cog, interaction, amount=10, filter_mode="all", channel=None)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        self.assertEqual(channel.purge.call_args[1]["limit"], 10)
        self.assertTrue(callable(channel.purge.call_args[1]["check"]))
        interaction.followup.send.assert_called_once()
        embed = interaction.followup.send.call_args[1]["embed"]
        self.assertIn("3", embed.description)

    async def test_cleanup_missing_permissions(self):
        interaction = self._create_mock_interaction()
        channel = MagicMock(spec=discord.TextChannel)
        channel.mention = "#restricted"
        channel.guild.me = MagicMock()
        channel.permissions_for.return_value.manage_messages = False
        interaction.channel = channel

        await self.cog.cleanup.callback(self.cog, interaction, amount=10, filter_mode="all", channel=None)

        interaction.followup.send.assert_called_once()
        msg = interaction.followup.send.call_args[0][0]
        self.assertIn("lacks `Manage Messages` permission", msg)

    async def test_clean_arena_sweeps_channels(self):
        interaction = self._create_mock_interaction()
        guild = MagicMock()
        interaction.guild = guild

        hub_channel = MagicMock(spec=discord.TextChannel)
        hub_channel.mention = "#game-hub"
        hub_channel.permissions_for.return_value.manage_messages = True
        hub_channel.purge = AsyncMock(return_value=[MagicMock(), MagicMock()])

        spec_channel = MagicMock(spec=discord.TextChannel)
        spec_channel.mention = "#spectators"
        spec_channel.permissions_for.return_value.manage_messages = True
        spec_channel.purge = AsyncMock(return_value=[MagicMock()])

        async def fake_resolve(g, key):
            if key == "game-hub":
                return hub_channel
            if key == "spectators":
                return spec_channel
            return None

        self.mock_router.resolve.side_effect = fake_resolve

        await self.cog.clean_arena.callback(self.cog, interaction, amount=50)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        hub_channel.purge.assert_called_once_with(limit=50)
        spec_channel.purge.assert_called_once_with(limit=50)
        interaction.followup.send.assert_called_once()

if __name__ == "__main__":
    unittest.main()
