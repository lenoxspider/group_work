"""Persistent MOVE button view for Red Light Green Light."""

import logging
from typing import Optional

import discord

from src.interface.channel_router import ChannelRouter
from src.plugins.games.formatters import build_ephemeral_move_feedback

logger = logging.getLogger("plugins.games.move_view")


class MoveView(discord.ui.View):
    """Persistent tap-to-move View with a single custom_id='rlgl:move' button."""

    def __init__(self, arena, channel_router: Optional[ChannelRouter] = None):
        super().__init__(timeout=None)
        self.arena = arena
        self.channel_router = channel_router

    @discord.ui.button(label="MOVE", style=discord.ButtonStyle.danger, custom_id="rlgl:move")
    async def move_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        try:
            await interaction.response.defer(ephemeral=True)
        except discord.NotFound:
            return

        if self.channel_router and interaction.guild:
            hub = await self.channel_router.resolve(interaction.guild, "game-hub")
            if hub and interaction.channel_id != hub.id:
                await interaction.followup.send(
                    f"Wrong Arena: You can only tap MOVE inside {hub.mention}!", ephemeral=True
                )
                return

        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        try:
            res = await self.arena.handle_move(guild_id, user_id)
            feedback = build_ephemeral_move_feedback(res)
            await interaction.followup.send(feedback, ephemeral=True)
        except Exception as e:
            await interaction.followup.send(f"{str(e)}", ephemeral=True)