"""Shop service - sell cosmetics, burn the spi."""

import logging
from datetime import datetime, timezone
from typing import List, Optional, Tuple

import discord

from src.plugins.shop.domain import BY_ID, CATALOGUE, Item
from src.plugins.shop.repository import SQLiteShopRepository

logger = logging.getLogger("plugins.shop.service")


class ShopError(Exception):
    """A purchase refusal that is safe to show the buyer verbatim."""


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ShopService:
    def __init__(self, repo: SQLiteShopRepository):
        self.repo = repo
        self.bank = None

    def attach_bank(self, bank) -> None:
        self.bank = bank

    @staticmethod
    def catalogue() -> List[Item]:
        return CATALOGUE

    @staticmethod
    def get(item_id: str) -> Optional[Item]:
        return BY_ID.get((item_id or "").strip().lower())

    async def owned(self, guild_id: str, user_id: str) -> List[str]:
        return await self.repo.list_owned(guild_id, user_id)

    async def total_burned(self, guild_id: str) -> int:
        return await self.repo.total_burned(guild_id)

    async def buy(
        self, guild: discord.Guild, member: discord.Member, item_id: str
    ) -> Tuple[Item, discord.Role]:
        item = self.get(item_id)
        if not item:
            raise ShopError(f"No such item `{item_id}`. Browse the catalogue with `/shop view`.")
        if not self.bank:
            raise ShopError("The bank is not wired. The shop is closed.")

        guild_id, user_id = str(guild.id), str(member.id)
        if await self.repo.owns(guild_id, user_id, item.item_id):
            raise ShopError(f"You already own **{item.name}**.")

        balance = await self.bank.balance(guild_id, user_id)
        if balance < item.price:
            raise ShopError(
                f"**{item.name}** costs **{item.price:,} spi**. You hold **{balance:,} spi**."
            )

        role = await self._ensure_role(guild, item)

        # Deliver first, charge second. If the burn fails we can always take the
        # role back; we can never un-take spi we failed to deliver against.
        try:
            await member.add_roles(role, reason=f"Purchased {item.name}")
        except discord.Forbidden:
            raise ShopError(
                "Discord will not let me hand out that role - my role has to sit above it "
                "in the hierarchy. No spi was taken."
            )
        except Exception as e:
            raise ShopError(f"Discord refused the role ({e}). No spi was taken.")

        try:
            await self.bank.burn(guild_id, user_id, item.price, f"shop: {item.name}")
        except Exception as e:
            try:
                await member.remove_roles(role, reason="Purchase rolled back")
            except Exception:
                pass
            raise ShopError(f"Could not take the spi ({e}). Purchase cancelled.")

        await self.repo.record(
            guild_id, user_id, item.item_id, item.price, str(role.id), _utcnow()
        )
        logger.info("%s bought %s for %s spi (burned)", user_id, item.item_id, item.price)
        return item, role

    async def _ensure_role(self, guild: discord.Guild, item: Item) -> discord.Role:
        role = discord.utils.get(guild.roles, name=item.name)
        if role:
            if role.colour.value != item.color or role.hoist != item.hoist:
                try:
                    await role.edit(
                        colour=discord.Colour(item.color),
                        hoist=item.hoist,
                        reason="Shop catalogue",
                    )
                except Exception as e:
                    logger.warning("Could not refresh role %s: %s", item.name, e)
            return role
        role = await guild.create_role(
            name=item.name,
            colour=discord.Colour(item.color),
            hoist=item.hoist,
            mentionable=False,
            reason=f"Shop cosmetic: {item.name}",
        )
        await self._raise_below_bot(guild, role)
        return role

    async def _raise_below_bot(self, guild: discord.Guild, role: discord.Role) -> None:
        """Nudge a new cosmetic above the arena roles, or its colour never shows.

        Discord picks a member's name colour from the highest-positioned role
        that has one, and create_role() drops new roles at the bottom - below
        Player and Spectator, which are both coloured. Without this, an arena
        player pays for a colour and keeps seeing teal.
        """
        try:
            top = guild.me.top_role.position
            if role.position >= top:
                return
            await role.edit(position=top - 1, reason="Cosmetic must outrank arena roles")
        except Exception as e:
            # Purely cosmetic: the purchase still stands if the move is refused.
            logger.warning("Could not raise cosmetic role %s: %s", role.name, e)
