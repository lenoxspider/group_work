"""Chronicle Cog - posts recorded history to #chronicle and reads it back."""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.interface.channel_router import ChannelRouter
from src.plugins.chronicle.service import ChronicleService

logger = logging.getLogger("plugins.chronicle.cog")

PINK = discord.Color.from_rgb(255, 0, 144)


class ChronicleCog(commands.Cog, name="Chronicle"):
    chronicle = app_commands.Group(
        name="chronicle", description="The collective's recorded history"
    )

    def __init__(
        self,
        bot: commands.Bot,
        service: ChronicleService,
        channel_router: Optional[ChannelRouter] = None,
    ):
        self.bot = bot
        self.service = service
        self.channel_router = channel_router
        self.post_loop.start()

    def cog_unload(self):
        self.post_loop.cancel()

    async def _channel(self, guild: discord.Guild):
        if self.channel_router:
            return await self.channel_router.resolve(guild, "chronicle")
        return discord.utils.get(guild.text_channels, name="chronicle")

    @tasks.loop(seconds=20)
    async def post_loop(self):
        """Post recorded-but-unposted entries. Retries next tick if the channel
        is missing or a send fails, so history is never silently dropped."""
        try:
            entries = await self.service.repo.list_unposted(limit=25)
        except Exception as e:
            logger.warning("Chronicle post loop read failed: %s", e)
            return
        for entry in entries:
            guild = self.bot.get_guild(int(entry["guild_id"]))
            if not guild:
                # Orphaned entry (bot left the guild) - drop it so it cannot loop.
                await self.service.repo.mark_posted(entry["id"])
                continue
            channel = await self._channel(guild)
            if not channel:
                continue  # #chronicle not provisioned yet; retry next tick
            try:
                await channel.send(entry["text"])
                await self.service.repo.mark_posted(entry["id"])
            except Exception as e:
                logger.warning("Could not post chronicle entry %s: %s", entry["id"], e)

    @post_loop.before_loop
    async def before_post_loop(self):
        await self.bot.wait_until_ready()

    @chronicle.command(name="recent", description="Read the recent history of the collective")
    @app_commands.describe(limit="How many entries (1-25)")
    async def chronicle_recent(self, interaction: discord.Interaction, limit: int = 10):
        await interaction.response.defer(ephemeral=True)
        entries = await self.service.recent(str(interaction.guild_id), min(max(limit, 1), 25))
        if not entries:
            await interaction.followup.send(
                "📜 The chronicle is empty. Nothing has been recorded yet.", ephemeral=True
            )
            return
        embed = discord.Embed(title="📜 THE CHRONICLE", color=PINK)
        embed.description = "\n\n".join(e["text"] for e in entries)[:4000]
        embed.set_footer(text=f"Last {len(entries)} entries, oldest first")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @chronicle.command(name="state", description="A digest of what the chronicle holds")
    async def chronicle_state(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = str(interaction.guild_id)
        counts = await self.service.counts(gid)
        recent = await self.service.recent(gid, 1)
        if not counts:
            await interaction.followup.send(
                "📜 The chronicle holds nothing yet.", ephemeral=True
            )
            return
        labels = {
            "citizen_signed": "Citizens signed",
            "court_verdict": "Court verdicts",
            "games_concluded": "Games concluded",
            "snap_trial": "Snap Trials",
            "law_enacted": "Laws enacted",
            "law_repealed": "Laws repealed",
            "proposal_concluded": "Proposals resolved",
        }
        lines = [f"**{labels.get(k, k)}:** {v}" for k, v in sorted(counts.items())]
        embed = discord.Embed(
            title="🏛️ STATE OF THE COLLECTIVE",
            description="\n".join(lines),
            color=PINK,
        )
        if recent:
            embed.add_field(name="Latest entry", value=recent[-1]["text"][:1000], inline=False)
        embed.set_footer(text="Recorded by the state, in its own hand.")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @chronicle.command(name="reconstruct", description="[Admin] Backfill the chronicle from the server's existing history")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def chronicle_reconstruct(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        count = await self.service.reconstruct_history(str(interaction.guild_id))
        if count == 0:
            await interaction.followup.send(
                "The chronicle already has entries, or there was nothing to reconstruct. "
                "It only runs on an empty chronicle, so it can never duplicate history.",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"📜 Reconstructed **{count}** entries from the ledger. They will appear "
                "in #chronicle shortly, oldest first.",
                ephemeral=True,
            )
