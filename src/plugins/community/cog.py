"""Community Cog - onboarding, the constitution sign, and membership status."""

import logging
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from src.interface.channel_router import ChannelRouter
from src.plugins.community.domain import CATIZEN, CITIZEN
from src.plugins.community.service import CommunityService

logger = logging.getLogger("plugins.community.cog")

PINK = discord.Color.from_rgb(255, 0, 144)


class CommunityCog(commands.Cog, name="Community"):
    def __init__(
        self,
        bot: commands.Bot,
        service: CommunityService,
        channel_router: Optional[ChannelRouter] = None,
    ):
        self.bot = bot
        self.service = service
        self.channel_router = channel_router

    async def _new_recruits_channel(self, guild: discord.Guild):
        if self.channel_router:
            return await self.channel_router.resolve(guild, "new-recruits")
        return discord.utils.get(guild.text_channels, name="new-recruits")

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        if member.bot:
            return
        guild_id = str(member.guild.id)
        user_id = str(member.id)
        await self.service.on_join(guild_id, user_id)

        ch = await self._new_recruits_channel(member.guild)
        embed = discord.Embed(
            title="🐱 A catizen has wandered in",
            description=(
                f"**{member.display_name}** just joined, and is a **catizen** until they "
                "sign the constitution.\n\n"
                "Two steps to become a citizen:\n"
                "• Post an intro here - that's Task #1 (pays 50 spi)\n"
                "• Run `/join` to sign the constitution and unlock voting"
            ),
            color=PINK,
        )
        if ch:
            try:
                await ch.send(content=member.mention, embed=embed)
            except Exception as e:
                logger.warning("Could not welcome %s: %s", user_id, e)

        try:
            await member.send(
                "Welcome to the collective, catizen 🐱\n\n"
                "Two steps to become a citizen:\n"
                "1. Post a quick intro in #new-recruits - that's Task #1, and it pays 50 spi.\n"
                "2. Run `/join` to sign the constitution and unlock voting.\n\n"
                "`/guide` lists every command. `/me` shows your standing."
            )
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        if message.channel.name != "new-recruits":
            return
        guild_id = str(message.guild.id)
        user_id = str(message.author.id)
        member = await self.service.get_member(guild_id, user_id)
        if member.intro_done or not member.intro_task_id:
            return
        await self.service.complete_intro(guild_id, user_id)
        try:
            await message.add_reaction("🎖️")
        except Exception:
            pass
        try:
            await message.channel.send(
                f"🎖️ **{message.author.display_name}** completed Task #1 (their intro). +50 spi."
            )
        except Exception:
            pass

    @app_commands.command(name="join", description="Sign the constitution and become a citizen")
    async def join(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        laws = await self.service.list_laws(guild_id)
        member = await self.service.sign(guild_id, user_id)

        if member.status == CITIZEN:
            law_lines = (
                "\n".join(f"• {law.title}" for law in laws[:10])
                if laws
                else "• (no laws on the books yet)"
            )
            embed = discord.Embed(
                title="○ △ □ CONSTITUTION ACCEPTED",
                description=(
                    f"**{interaction.user.display_name}**, you are now a **citizen**. 🗳️\n\n"
                    "Voting in `/society` is unlocked. You accept the current constitution:\n"
                    + law_lines
                ),
                color=PINK,
            )
            embed.set_footer(text="Welcome, comrade. Earn rank via /report.")
        else:
            embed = discord.Embed(
                title="Already a citizen",
                description="You've already signed the constitution.",
                color=PINK,
            )
        await interaction.followup.send(embed=embed)

    @app_commands.command(name="me", description="Your membership status, intro task, and wallet")
    async def me(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        member = await self.service.get_member(guild_id, user_id)
        balance = 0
        if self.service.bank:
            try:
                balance = await self.service.bank.balance(guild_id, user_id)
            except Exception:
                pass

        status_display = "🐱 Catizen" if member.status == CATIZEN else "🗳️ Citizen"
        intro = "✅ done" if member.intro_done else "⏳ pending (post in #new-recruits)"

        embed = discord.Embed(title=f"Identity of {interaction.user.display_name}", color=PINK)
        embed.add_field(name="Membership", value=f"**{status_display}**", inline=True)
        embed.add_field(name="Intro task", value=intro, inline=True)
        embed.add_field(name="Wallet", value=f"`{balance:,} spi`", inline=True)
        if member.status == CATIZEN:
            embed.set_footer(text="Run /join to sign the constitution and become a citizen.")
        await interaction.followup.send(embed=embed)