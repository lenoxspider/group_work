"""Persistent Left/Right view for the Glass Bridge."""

import logging
from typing import Optional

import discord

from src.interface.channel_router import ChannelRouter
from src.plugins.games.formatters import build_bridge_feedback

logger = logging.getLogger("plugins.games.bridge_view")


class BridgeView(discord.ui.View):
    """Two persistent buttons, custom_ids gb:left / gb:right.

    Turn enforcement lives in the game module, not here: a click from anyone but
    the current player raises NotYourTurn, which the arena surfaces as a
    ValidationError and this view reports back ephemerally.
    """

    def __init__(self, arena, channel_router: Optional[ChannelRouter] = None):
        super().__init__(timeout=None)
        self.arena = arena
        self.channel_router = channel_router

    async def _choose(self, interaction: discord.Interaction, side: str) -> None:
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        if self.channel_router and interaction.guild:
            hub = await self.channel_router.resolve(interaction.guild, "game-hub")
            if hub and interaction.channel_id != hub.id:
                await interaction.followup.send(
                    f"Wrong Arena: you can only cross inside {hub.mention}!", ephemeral=True
                )
                return

        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)
        try:
            move = await self.arena.handle_choice(guild_id, user_id, side)
            await interaction.followup.send(build_bridge_feedback(move), ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"{e}", ephemeral=True)

    @discord.ui.button(label="◀ Left", style=discord.ButtonStyle.primary, custom_id="gb:left")
    async def left(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._choose(interaction, "left")

    @discord.ui.button(label="Right ▶", style=discord.ButtonStyle.primary, custom_id="gb:right")
    async def right(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._choose(interaction, "right")
