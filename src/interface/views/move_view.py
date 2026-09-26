"""
Persistent Discord UI View for Squid Game Red Light Green Light.

What it does:
- Provides a persistent discord.ui.View with a single button (custom_id="rlgl:move").
- Immutable button label "MOVE" (never relabeled or greyed out between phases).
- Enforces interaction response deferral and delegates to SquidService.handle_move.
- Formats ephemeral 3-line feedback for the acting contestant.

What it does NOT do:
- Does NOT alter button label or disable the button based on phase.
"""

import logging
from typing import Optional
import discord

from src.application.services.squid_service import SquidService
from src.interface.squid_formatters import build_ephemeral_move_feedback
from src.interface.channel_router import ChannelRouter

logger = logging.getLogger("interface.views.move_view")

class MoveView(discord.ui.View):
    """Persistent tap-to-move View attached to the Red Light Green Light track message."""

    def __init__(
        self,
        squid_service: SquidService,
        channel_router: Optional[ChannelRouter] = None
    ):
        super().__init__(timeout=None)
        self.squid_service = squid_service
        self.channel_router = channel_router

    @discord.ui.button(
        label="MOVE",
        style=discord.ButtonStyle.danger,
        custom_id="rlgl:move"
    )
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        """Processes a tap on the MOVE button."""
        # 1. interaction.response.defer(ephemeral=True)
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        if self.channel_router and interaction.guild:
            hub = await self.channel_router.resolve(interaction.guild, "game-hub")
            if hub and interaction.channel_id != hub.id:
                await interaction.followup.send(
                    f"⚠️ **Wrong Arena:** You can only tap MOVE inside {hub.mention}!",
                    ephemeral=True
                )
                return

        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        try:
            res = await self.squid_service.handle_move(guild_id, user_id)
            feedback = build_ephemeral_move_feedback(res)
            await interaction.followup.send(feedback, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"⚠️ {str(e)}", ephemeral=True)
