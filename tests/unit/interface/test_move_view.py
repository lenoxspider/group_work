"""
Unit tests for MoveView persistent UI component.
"""

import unittest
from unittest.mock import AsyncMock, MagicMock
from src.interface.views.move_view import MoveView
from src.application.dtos.squid_dtos import RedLightMoveResultDTO

class TestMoveView(unittest.IsolatedAsyncioTestCase):

    def test_view_properties(self):
        service = MagicMock()
        view = MoveView(service)
        self.assertIsNone(view.timeout)
        self.assertEqual(len(view.children), 1)
        button = view.children[0]
        self.assertEqual(button.custom_id, "rlgl:move")
        self.assertEqual(button.label, "MOVE")

    async def test_button_interaction_defer_and_handle_move(self):
        service = MagicMock()
        res_dto = RedLightMoveResultDTO(
            guild_id="123",
            user_id="456",
            player_number="001",
            survived=True,
            distance=20,
            is_finished=False,
            advance=20,
            target=100,
            rank=1,
            total_racers=1,
            status_code="ok",
            status_message="Safe step!"
        )
        service.handle_move = AsyncMock(return_value=res_dto)

        view = MoveView(service)
        interaction = AsyncMock()
        interaction.guild_id = 123
        interaction.user.id = 456
        interaction.guild = None

        await view.move_button.callback(interaction)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        service.handle_move.assert_called_once_with("123", "456")
        interaction.followup.send.assert_called_once()
        sent_text = interaction.followup.send.call_args[0][0]
        self.assertIn("+20m → 20m/100m", sent_text)
        self.assertTrue(interaction.followup.send.call_args[1].get("ephemeral"))

    async def test_button_wrong_arena_rejection(self):
        service = MagicMock()
        router = AsyncMock()
        hub_channel = MagicMock()
        hub_channel.id = 777
        hub_channel.mention = "<#777>"
        router.resolve.return_value = hub_channel

        view = MoveView(service, channel_router=router)
        interaction = AsyncMock()
        interaction.guild_id = 123
        interaction.user.id = 456
        interaction.guild = MagicMock()
        interaction.channel_id = 999  # Not the game-hub

        await view.move_button.callback(interaction)

        interaction.response.defer.assert_called_once_with(ephemeral=True)
        interaction.followup.send.assert_called_once()
        sent_text = interaction.followup.send.call_args[0][0]
        self.assertIn("Wrong Arena", sent_text)
        # Should not call handle_move when outside arena
        service.handle_move.assert_not_called()

if __name__ == "__main__":
    unittest.main()
