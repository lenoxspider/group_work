"""Society slash commands - laws, citizenship, treasury, and proposals."""

import logging
from typing import Optional, Literal

import discord
from discord import app_commands
from discord.ext import commands

from src.interface.discord_formatters import COLOR_PRIMARY, COLOR_SUCCESS
from src.plugins.society.domain import SocietyError
from src.plugins.society.service import SocietyService

logger = logging.getLogger("plugins.society.cog")


class SocietyCog(commands.Cog, name="Society"):
    def __init__(self, bot: commands.Bot, service: SocietyService):
        self.bot = bot
        self.service = service

    law = app_commands.Group(name="law", description="The constitution - society rules")
    society = app_commands.Group(name="society", description="Governance, treasury, and proposals")

    # --- Laws ---

    @law.command(name="add", description="[Admin] Enact a new law")
    @app_commands.describe(title="Short name", description="Law text", fine="spi fine for breaking it")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def law_add(self, interaction: discord.Interaction, title: str, description: str, fine: int = 0):
        await interaction.response.defer()
        law = await self.service.add_law(str(interaction.guild_id), title, description, fine)
        await interaction.followup.send(
            f"⚖️ **Law enacted** `{law.law_id}`: **{law.title}**" + (f" (fine: {law.fine_amount} spi)" if law.fine_amount else "")
        )

    @law.command(name="list", description="List every law")
    async def law_list(self, interaction: discord.Interaction):
        await interaction.response.defer()
        laws = await self.service.list_laws(str(interaction.guild_id))
        if not laws:
            await interaction.followup.send("No laws yet. Anarchy reigns.")
            return
        embed = discord.Embed(title="⚖️ The Constitution", color=COLOR_PRIMARY)
        for law in laws:
            value = law.description + (f"\n*Fine: {law.fine_amount} spi*" if law.fine_amount else "")
            embed.add_field(name=f"`{law.law_id}` — {law.title}", value=value, inline=False)
        await interaction.followup.send(embed=embed)

    @law.command(name="show", description="Cite a specific law")
    @app_commands.describe(law_id="Law ID (e.g. LAW-A1B2C3)")
    async def law_show(self, interaction: discord.Interaction, law_id: str):
        law = await self.service.get_law(law_id.strip().upper())
        if not law:
            await interaction.response.send_message(f"❌ No law `{law_id}`.", ephemeral=True)
            return
        embed = discord.Embed(title=f"⚖️ `{law.law_id}` — {law.title}", description=law.description, color=COLOR_PRIMARY)
        if law.fine_amount:
            embed.add_field(name="Fine", value=f"{law.fine_amount} spi", inline=False)
        await interaction.response.send_message(embed=embed)

    @law.command(name="remove", description="[Admin] Repeal a law")
    @app_commands.describe(law_id="Law ID to repeal")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def law_remove(self, interaction: discord.Interaction, law_id: str):
        await interaction.response.defer()
        try:
            await self.service.remove_law(law_id.strip().upper())
            await interaction.followup.send(f"🗑️ Law `{law_id}` repealed.")
        except SocietyError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)

    # --- Society ---

    @society.command(name="status", description="Your citizenship tier and balance")
    async def status(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        await interaction.response.defer()
        balance, title, threshold, next_tier = await self.service.citizenship(str(interaction.guild_id), str(target.id))
        embed = discord.Embed(title=f"🏛️ {target.display_name} — {title}", color=COLOR_SUCCESS)
        embed.add_field(name="Balance", value=f"{balance:,} spi", inline=True)
        embed.add_field(name="Tier threshold", value=f"{threshold:,} spi", inline=True)
        if next_tier:
            embed.add_field(name="Next rank", value=next_tier, inline=False)
        await interaction.followup.send(embed=embed)

    @society.command(name="treasury", description="The society treasury and net minted supply")
    async def treasury(self, interaction: discord.Interaction):
        await interaction.response.defer()
        treasury = await self.service.treasury_balance(str(interaction.guild_id))
        in_circulation = -treasury
        embed = discord.Embed(title="🏛️ Society Treasury", color=COLOR_PRIMARY)
        embed.add_field(name="Net minted", value=f"{-treasury:,} spi in circulation", inline=False)
        embed.add_field(name="Treasury account", value=f"{treasury:,} spi", inline=True)
        await interaction.followup.send(embed=embed)

    @society.command(name="propose", description="Submit a proposal for democratic vote")
    @app_commands.describe(title="Proposal title", amount="spi requested from the treasury (0 for non-spending)", description="What and why")
    async def propose(self, interaction: discord.Interaction, title: str, description: str, amount: int = 0):
        await interaction.response.defer()
        proposal = await self.service.propose(str(interaction.guild_id), str(interaction.user.id), title, description, amount)
        await interaction.followup.send(
            f"🗳️ **Proposal `{proposal.proposal_id}`**: {proposal.title}"
            + (f" — requests **{proposal.amount:,} spi**" if proposal.amount else "")
            + "\nVote with `/society vote {proposal.proposal_id} yes|no`."
        )

    @society.command(name="vote", description="Vote on an open proposal")
    @app_commands.describe(proposal_id="Proposal ID", decision="Your vote")
    async def vote(self, interaction: discord.Interaction, proposal_id: str, decision: Literal["yes", "no"]):
        await interaction.response.defer()
        try:
            proposal = await self.service.vote(str(interaction.guild_id), proposal_id.strip().upper(), str(interaction.user.id), decision)
            yes = len(proposal.approvers())
            no = len(proposal.rejectors())
            await interaction.followup.send(f"🗳️ Vote recorded. `{proposal.proposal_id}`: **{yes} yes · {no} no**")
        except SocietyError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)

    @society.command(name="conclude", description="[Admin] Resolve a proposal by majority vote")
    @app_commands.describe(proposal_id="Proposal ID")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def conclude(self, interaction: discord.Interaction, proposal_id: str):
        await interaction.response.defer()
        try:
            proposal = await self.service.conclude(str(interaction.guild_id), proposal_id.strip().upper())
            yes, no = len(proposal.approvers()), len(proposal.rejectors())
            payout = f" — **{proposal.amount:,} spi** granted" if proposal.status == "APPROVED" and proposal.amount else ""
            await interaction.followup.send(
                f"🏛️ `{proposal.proposal_id}` **{proposal.status}** ({yes} yes · {no} no){payout}"
            )
        except SocietyError as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)

    @society.command(name="proposals", description="List open proposals")
    async def proposals(self, interaction: discord.Interaction):
        await interaction.response.defer()
        proposals = await self.service.list_proposals(str(interaction.guild_id), status="OPEN")
        if not proposals:
            await interaction.followup.send("No open proposals.")
            return
        embed = discord.Embed(title="🗳️ Open Proposals", color=COLOR_PRIMARY)
        for p in proposals:
            embed.add_field(
                name=f"`{p.proposal_id}` — {p.title}",
                value=f"By <@{p.author_id}> • {len(p.approvers())} yes / {len(p.rejectors())} no"
                      + (f"\nRequests **{p.amount:,} spi**" if p.amount else ""),
                inline=False,
            )
        await interaction.followup.send(embed=embed)