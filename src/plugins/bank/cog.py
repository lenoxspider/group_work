"""Bank slash commands and presentation."""

import discord
from discord import app_commands
from discord.ext import commands

from src.plugins.bank.domain import InsufficientFunds, InvalidAmount, SelfTransfer, SINK, TREASURY
from src.plugins.bank.service import BankService
from src.plugins.community.checks import requires_citizen


def _label(user_id: str, bot: commands.Bot) -> str:
    if user_id == TREASURY:
        return "Treasury"
    if user_id == SINK:
        return "Sink"
    user = bot.get_user(int(user_id))
    return user.display_name if user else user_id


class BankCog(commands.Cog):
    def __init__(self, bot: commands.Bot, service: BankService):
        self.bot = bot
        self.service = service

    bank = app_commands.Group(name="bank", description="Manage spi finances")

    @bank.command(name="balance", description="Check a member's spi balance")
    @app_commands.describe(member="Member to inspect (defaults to you)")
    async def balance(self, interaction: discord.Interaction, member: discord.Member = None):
        target = member or interaction.user
        gid = str(interaction.guild_id)
        await self.service.ensure_account(gid, str(target.id))
        bal = await self.service.balance(gid, str(target.id))
        await interaction.response.send_message(
            f"🏦 **{target.display_name}** holds **{bal:,} spi**"
        )

    @bank.command(name="give", description="Send spi to another member")
    @app_commands.describe(member="Recipient", amount="Amount of spi", reason="Optional note")
    @requires_citizen()
    async def give(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: int,
        reason: str = "",
    ):
        gid = str(interaction.guild_id)
        try:
            await self.service.transfer(gid, str(interaction.user.id), str(member.id), amount, reason)
        except (InsufficientFunds, InvalidAmount, SelfTransfer) as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"💸 **{interaction.user.display_name}** → **{member.display_name}**: {amount:,} spi" + (f" ({reason})" if reason else "")
        )

    @bank.command(name="ledger", description="Your recent spi transactions")
    async def ledger(self, interaction: discord.Interaction):
        gid = str(interaction.guild_id)
        txs = await self.service.ledger(gid, str(interaction.user.id), limit=15)
        if not txs:
            await interaction.response.send_message("No transactions yet.", ephemeral=True)
            return
        lines = []
        for t in txs:
            frm = _label(t.from_user, self.bot)
            to = _label(t.to_user, self.bot)
            lines.append(f"`{t.created_at[:16]}Z` {frm} → {to}: **{t.amount:,}** spi" + (f" — {t.reason}" if t.reason else ""))
        await interaction.response.send_message("**Ledger**\n" + "\n".join(lines[:15]))

    @bank.command(name="grant", description="[Admin] Mint spi from the treasury")
    @app_commands.describe(member="Recipient", amount="Amount of spi", reason="Optional note")
    @app_commands.checks.has_permissions(administrator=True)
    async def grant(self, interaction: discord.Interaction, member: discord.Member, amount: int, reason: str = ""):
        gid = str(interaction.guild_id)
        try:
            await self.service.grant(gid, str(member.id), amount, reason)
        except (InvalidAmount,) as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"🏛️ Treasury minted **{amount:,} spi** to **{member.display_name}**" + (f" ({reason})" if reason else "")
        )

    @bank.command(name="burn", description="[Admin] Remove spi from circulation")
    @app_commands.describe(member="Target", amount="Amount of spi", reason="Optional note")
    @app_commands.checks.has_permissions(administrator=True)
    async def burn(self, interaction: discord.Interaction, member: discord.Member, amount: int, reason: str = ""):
        gid = str(interaction.guild_id)
        try:
            await self.service.burn(gid, str(member.id), amount, reason)
        except (InsufficientFunds, InvalidAmount, SelfTransfer) as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"🔥 **{amount:,} spi** burned from **{member.display_name}**" + (f" ({reason})" if reason else "")
        )