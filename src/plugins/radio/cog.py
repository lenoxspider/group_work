"""Radio slash commands."""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.plugins.radio.domain import NoActivePlayer, RadioError
from src.plugins.radio.service import RadioService
from src.interface.discord_formatters import COLOR_PRIMARY

logger = logging.getLogger("plugins.radio.cog")


def _fmt_duration(seconds: int) -> str:
    if not seconds:
        return "?:??"
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


class RadioCog(commands.Cog, name="Radio"):
    def __init__(self, bot: commands.Bot, service: RadioService):
        self.bot = bot
        self.service = service

    radio = app_commands.Group(name="radio", description="Radio station controls")

    @radio.command(name="play", description="Queue a YouTube link or search query")
    @app_commands.describe(query="YouTube URL or search term")
    async def play(self, interaction: discord.Interaction, query: str):
        member = interaction.user
        voice = getattr(member, "voice", None)
        if not voice or not voice.channel:
            await interaction.response.send_message("❌ Join a voice channel first.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            track = await self.service.play(
                str(interaction.guild_id), voice.channel, query, str(interaction.user.id)
            )
            queued = len(self.service.queue(str(interaction.guild_id)))
            label = f"Queued (position {queued + 1})" if queued else "Now playing"
            embed = discord.Embed(
                title=f"🎵 {label}: {track.title}",
                description=f"Duration: {_fmt_duration(track.duration)}",
                color=COLOR_PRIMARY,
            )
            await interaction.followup.send(embed=embed)
        except RadioError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)

    @radio.command(name="skip", description="Skip the current track")
    async def skip(self, interaction: discord.Interaction):
        if not self._is_controller(interaction):
            await interaction.response.send_message("❌ You need the DJ role or Manage Channels permission.", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            current = await self.service.skip(str(interaction.guild_id))
            await interaction.followup.send(
                f"⏭️ Skipped. Now playing: **{current.title}**" if current else "⏭️ Skipped. Queue is empty."
            )
        except RadioError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)

    @radio.command(name="stop", description="Stop the radio and disconnect")
    async def stop(self, interaction: discord.Interaction):
        if not self._is_controller(interaction):
            await interaction.response.send_message("❌ You need the DJ role or Manage Channels permission.", ephemeral=True)
            return
        await interaction.response.defer()
        await self.service.stop(str(interaction.guild_id))
        await interaction.followup.send("📻 Radio stopped.")

    @radio.command(name="queue", description="Show the upcoming queue")
    async def queue(self, interaction: discord.Interaction):
        await interaction.response.defer()
        current = self.service.current(str(interaction.guild_id))
        upcoming = self.service.queue(str(interaction.guild_id))
        embed = discord.Embed(title="📻 Radio Queue", color=COLOR_PRIMARY)
        if current:
            embed.add_field(name="Now playing", value=f"**{current.title}** ({_fmt_duration(current.duration)})", inline=False)
        if not upcoming:
            embed.add_field(name="Up next", value="Queue is empty.", inline=False)
        else:
            lines = []
            for i, t in enumerate(upcoming[:10], start=1):
                lines.append(f"`{i}.` **{t.title}** ({_fmt_duration(t.duration)}) <@{t.requester_id}>")
            embed.add_field(name="Up next", value="\n".join(lines), inline=False)
        await interaction.followup.send(embed=embed)

    @radio.command(name="now", description="Show what is currently playing")
    async def now(self, interaction: discord.Interaction):
        current = self.service.current(str(interaction.guild_id))
        if not current:
            await interaction.response.send_message("📻 Nothing is playing.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"📻 Now playing: {current.title}",
            description=f"Requested by <@{current.requester_id}> • {_fmt_duration(current.duration)}",
            color=COLOR_PRIMARY,
        )
        await interaction.response.send_message(embed=embed)

    def _is_controller(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        perms = getattr(member, "guild_permissions", None)
        if perms and (perms.manage_channels or perms.administrator):
            return True
        dj_role = discord.utils.get(interaction.guild.roles, name="DJ")
        return dj_role is not None and getattr(member, "get_role", None) and member.get_role(dj_role.id) is not None