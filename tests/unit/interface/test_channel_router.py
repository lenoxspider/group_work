"""Unit tests for ChannelRouter fallback chain."""

import unittest
from unittest.mock import AsyncMock, MagicMock
from src.interface.channel_router import ChannelRouter

class TestChannelRouter(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.mock_bot = MagicMock()
        self.mock_repo = AsyncMock()
        self.router = ChannelRouter(self.mock_bot, self.mock_repo)

    async def test_get_resolves_from_persisted_binding(self):
        guild = MagicMock()
        guild.id = 12345
        self.mock_repo.get_binding.return_value = "999888"

        mock_channel = MagicMock(spec=["id", "name"])
        import discord
        # create mock that satisfies isinstance(discord.TextChannel)
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 999888
        mock_channel.name = "tasks"
        self.mock_bot.get_channel.return_value = mock_channel

        ch = await self.router.get(guild, "tasks")
        self.assertEqual(ch, mock_channel)
        self.mock_repo.get_binding.assert_called_once_with("12345", "tasks")

    async def test_get_auto_heals_from_name_lookup(self):
        guild = MagicMock()
        guild.id = 12345
        self.mock_repo.get_binding.return_value = None

        import discord
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.name = "deadlines"
        mock_channel.id = 777666
        guild.text_channels = [mock_channel]

        ch = await self.router.get(guild, "deadlines")
        self.assertEqual(ch, mock_channel)
        self.mock_repo.save_binding.assert_called_once()

    async def test_get_emergency_fallback(self):
        guild = MagicMock()
        guild.id = 12345
        self.mock_repo.get_binding.return_value = None
        guild.text_channels = []
        guild.categories = []

        import discord
        system_ch = MagicMock(spec=discord.TextChannel)
        system_ch.permissions_for.return_value.send_messages = True
        guild.system_channel = system_ch

        ch = await self.router.get(guild, "nonexistent")
        self.assertEqual(ch, system_ch)
        self.assertIn("12345:nonexistent", self.router.route_failures)

if __name__ == "__main__":
    unittest.main()
