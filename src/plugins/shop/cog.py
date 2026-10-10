"""Shop Cog - browse the catalogue, spend spi, watch it burn."""

import logging

import discord
from discord import app_commands
from discord.ext import commands

from src.plugins.community.checks import requires_citizen
from src.plugins.shop.domain import CATALOGUE
from src.plugins.shop.service import ShopError, ShopService

logger = logging.getLogger("plugins.shop.cog")

PINK = discord.Color.from_rgb(255, 0, 144)


class ShopCog(commands.Cog, name="Shop"):
    shop = app_commands.Group(
        name="shop", description="Spend spi on cosmetics - the collective's only sink"
    )

    def __init__(self, bot: commands.Bot, service: ShopService):
        self.bot = bot
        self.service = service

    @shop.command(name="view", description="The catalogue - what spi can actually buy")
    async def shop_view(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild_id = str(interaction.guild_id)
        user_id = str(interaction.user.id)

        owned = set(await self.service.owned(guild_id, user_id))
        # None, not 0: a failed ledger read must not be reported as poverty. The
        # cheapest cosmetic costs 300 spi, so "0 spi" reads as "you can never
        # afford anything" - a lie told about someone's own money.
        balance = None
        if self.service.bank:
            try:
                balance = await self.service.bank.balance(guild_id, user_id)
            except Exception:
                logger.error("Could not read the balance for /shop view (%s)", user_id, exc_info=True)

        holding = (
            f"You hold **{balance:,} spi**."
            if balance is not None
            else "Your balance could not be read just now - the prices below are still correct."
        )

        embed = discord.Embed(
            title="🛍️ THE SHOP",
            description=(
                f"{holding} Everything here is bought once, kept forever, "
                "and **burned on purchase** - it leaves circulation for good.\n\n"
                "Buy with `/shop buy item:<id>`."
            ),
            color=PINK,
        )
        for item in CATALOGUE:
            status = "✅ owned" if item.item_id in owned else f"**{item.price:,} spi**"
            embed.add_field(
                name=f"{item.name} · `{item.item_id}`",
                value=f"{item.blurb}\n{status}",
                inline=False,
            )
        burned = await self.service.total_burned(guild_id)
        embed.set_footer(text=f"Burned by this server so far: {burned:,} spi")
        await interaction.followup.send(embed=embed, ephemeral=True)

    @shop.command(name="buy", description="Buy a cosmetic. The spi is burned out of circulation.")
    @app_commands.describe(item="The item id from /shop view (e.g. pink, vip, square)")
    @requires_citizen()
    async def shop_buy(self, interaction: discord.Interaction, item: str):
        await interaction.response.defer()
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.followup.send("The shop only opens inside the server.", ephemeral=True)
            return

        try:
            bought, role = await self.service.buy(interaction.guild, interaction.user, item)
        except ShopError as e:
            await interaction.followup.send(f"⛔ {e}", ephemeral=True)
            return
        except Exception as e:
            logger.warning("Purchase of %s failed: %s", item, e)
            await interaction.followup.send(
                "The purchase failed. No spi was taken.", ephemeral=True
            )
            return

        embed = discord.Embed(
            title=f"{bought.name} ACQUIRED",
            description=(
                f"**{interaction.user.display_name}** spent **{bought.price:,} spi**, and it is "
                "**gone** - burned out of circulation.\n\n"
                f"{role.mention} is yours. Wear it."
            ),
            color=discord.Colour(bought.color),
        )
        await interaction.followup.send(embed=embed)

    @shop.command(name="inventory", description="The cosmetics you own")
    async def shop_inventory(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        owned = await self.service.owned(str(interaction.guild_id), str(interaction.user.id))
        if not owned:
            await interaction.followup.send(
                "You own nothing yet. Browse the catalogue with `/shop view`.", ephemeral=True
            )
            return
        by_id = {i.item_id: i for i in CATALOGUE}
        lines = [
            f"• **{by_id[o].name}** · {by_id[o].price:,} spi burned"
            for o in owned if o in by_id
        ]
        embed = discord.Embed(
            title="🛍️ Your shelf",
            description="\n".join(lines) or "• (nothing on record)",
            color=PINK,
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
