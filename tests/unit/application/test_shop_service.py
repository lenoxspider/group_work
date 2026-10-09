"""Unit tests for the shop service - the spi sink.

The purchase path is the one that matters: it moves money and grants a Discord
role, and it was originally verified with a throwaway script that was deleted
afterwards. These replace it.

The ordering rule is deliver-then-charge. The role is granted first and rolled
back if the burn fails, because taking spi and failing to deliver is worse than
the reverse.
"""

import os
import tempfile
import unittest

import aiosqlite
import discord

from src.plugins.shop.domain import BY_ID, CATALOGUE
from src.plugins.shop.repository import SQLiteShopRepository
from src.plugins.shop.schema import SHOP_SCHEMA
from src.plugins.shop.service import ShopError, ShopService

GUILD_ID = 1553052975876939876


class FakeResponse:
    status = 403
    reason = "Forbidden"


class FakeRole:
    def __init__(self, guild, role_id, name, color, hoist, position):
        self._guild = guild
        self.id = role_id
        self.name = name
        self.colour = discord.Colour(color)
        self.hoist = hoist
        self.position = position
        self.mention = f"<@&{role_id}>"
        self.edit_calls = []

    async def edit(self, **kwargs):
        self.edit_calls.append(kwargs.get("position"))
        if "position" in kwargs:
            target = kwargs["position"]
            top = self._guild.me.top_role.position
            # Discord displaces the roles in the way, but never the bot's own
            # top role - a bot cannot push itself higher.
            for role in self._guild.roles:
                if role is not self and target <= role.position < top:
                    role.position -= 1
            self.position = target


class FakeMe:
    def __init__(self, top_role):
        self.top_role = top_role


class FakeGuild:
    """Mirrors the live hierarchy: Spectator 1, Catizen 1, Player 2, bot 3."""

    def __init__(self):
        self.id = GUILD_ID
        self.roles = [
            FakeRole(self, 0, "@everyone", 0, False, 0),
            FakeRole(self, 1, "Spectator", 7895160, False, 1),
            FakeRole(self, 2, "Catizen", 13148260, False, 1),
            FakeRole(self, 3, "Player", 227958, False, 2),
            FakeRole(self, 4, "Tovarishch", 0, False, 3),
        ]
        self.me = FakeMe(self.roles[-1])
        self._next_id = 900000

    async def create_role(self, name, colour, hoist, mentionable, reason):
        self._next_id += 1
        # Discord drops new roles at the bottom, above @everyone.
        role = FakeRole(self, self._next_id, name, colour.value, hoist, 1)
        self.roles.append(role)
        return role


class FakeMember:
    def __init__(self, user_id, fail_add=False, fail_remove=False):
        self.id = int(user_id)
        self.fail_add = fail_add
        self.fail_remove = fail_remove
        self.added = []
        self.removed = []

    async def add_roles(self, role, reason=None):
        if self.fail_add:
            raise discord.Forbidden(FakeResponse(), "role hierarchy")
        self.added.append(role.name)

    async def remove_roles(self, role, reason=None):
        if self.fail_remove:
            raise discord.Forbidden(FakeResponse(), "role hierarchy")
        self.removed.append(role.name)


class FakeBank:
    def __init__(self, balance, fail_burn=False):
        self._balance = balance
        self.fail_burn = fail_burn
        self.burns = []
        # Any call here means spi moved somewhere other than out of circulation.
        self.non_burn_calls = []

    async def balance(self, guild_id, user_id):
        return self._balance

    async def burn(self, guild_id, user_id, amount, reason=""):
        if self.fail_burn:
            raise RuntimeError("sink unavailable")
        self.burns.append((user_id, amount, reason))

    async def transfer(self, *args, **kwargs):
        self.non_burn_calls.append(("transfer", args, kwargs))
        raise AssertionError("the shop must burn spi, not transfer it")

    async def grant(self, *args, **kwargs):
        self.non_burn_calls.append(("grant", args, kwargs))
        raise AssertionError("the shop must burn spi, not grant it")


class TestShopService(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".sqlite")
        os.close(fd)
        async with aiosqlite.connect(self.db_path) as db:
            for stmt in SHOP_SCHEMA:
                await db.execute(stmt)
            await db.commit()
        self.repo = SQLiteShopRepository(self.db_path)

    async def asyncTearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass

    def _service(self, balance=5000, fail_burn=False):
        service = ShopService(self.repo)
        service.attach_bank(FakeBank(balance, fail_burn=fail_burn))
        return service

    # --- catalogue ---

    def test_item_lookup_is_case_insensitive_and_trims(self):
        self.assertIs(ShopService.get("  PINK "), BY_ID["pink"])

    def test_unknown_item_lookup_returns_none(self):
        self.assertIsNone(ShopService.get("does-not-exist"))

    def test_every_catalogue_item_is_reachable_by_id(self):
        for item in CATALOGUE:
            self.assertIs(ShopService.get(item.item_id), item)

    def test_ids_are_unique(self):
        self.assertEqual(len({i.item_id for i in CATALOGUE}), len(CATALOGUE))

    def test_role_names_are_unique(self):
        """They double as Discord role names, so a clash would collide."""
        self.assertEqual(len({i.name for i in CATALOGUE}), len(CATALOGUE))

    # --- refusals ---

    async def test_unknown_item_is_refused(self):
        service = self._service()
        with self.assertRaises(ShopError):
            await service.buy(FakeGuild(), FakeMember("111"), "nope")
        self.assertEqual(service.bank.burns, [])

    async def test_insufficient_funds_is_refused_and_names_the_gap(self):
        service = self._service(balance=100)
        with self.assertRaises(ShopError) as ctx:
            await service.buy(FakeGuild(), FakeMember("111"), "vip")
        self.assertIn("1,500", str(ctx.exception))
        self.assertIn("100", str(ctx.exception))
        self.assertEqual(service.bank.burns, [])

    async def test_duplicate_purchase_is_refused_and_does_not_burn_again(self):
        service = self._service(balance=5000)
        guild, member = FakeGuild(), FakeMember("111")
        await service.buy(guild, member, "pink")
        self.assertEqual(len(service.bank.burns), 1)
        with self.assertRaises(ShopError):
            await service.buy(guild, member, "pink")
        self.assertEqual(len(service.bank.burns), 1, "duplicate purchase burned spi")

    async def test_missing_bank_closes_the_shop(self):
        service = ShopService(self.repo)  # no attach_bank
        with self.assertRaises(ShopError):
            await service.buy(FakeGuild(), FakeMember("111"), "pink")

    # --- the happy path ---

    async def test_purchase_burns_the_exact_price_and_records_it(self):
        service = self._service(balance=3150)
        guild, member = FakeGuild(), FakeMember("111")
        item, role = await service.buy(guild, member, "pink")

        self.assertEqual(item.item_id, "pink")
        self.assertEqual(service.bank.burns, [("111", item.price, "shop: ▢ Pink")])
        self.assertEqual(member.added, [item.name])
        self.assertEqual(role.name, item.name)
        self.assertTrue(await self.repo.owns(str(GUILD_ID), "111", "pink"))

    async def test_burn_goes_to_the_sink_not_the_treasury(self):
        """The whole point of the shop: spi must leave circulation entirely.

        A transfer to the treasury or a grant would both be silently wrong here
        - the money would still exist - so the fake bank records and rejects them.
        """
        service = self._service(balance=5000)
        await service.buy(FakeGuild(), FakeMember("111"), "gold")
        self.assertEqual(service.bank.non_burn_calls, [])
        self.assertEqual(len(service.bank.burns), 1)

    async def test_total_burned_accumulates_across_buyers(self):
        service = self._service(balance=9000)
        await service.buy(FakeGuild(), FakeMember("111"), "pink")   # 400
        await service.buy(FakeGuild(), FakeMember("222"), "guard")  # 700
        self.assertEqual(await service.total_burned(str(GUILD_ID)), 1100)

    async def test_owned_lists_only_what_that_member_bought(self):
        service = self._service(balance=9000)
        guild = FakeGuild()
        await service.buy(guild, FakeMember("111"), "pink")
        await service.buy(guild, FakeMember("222"), "guard")
        self.assertEqual(await service.owned(str(GUILD_ID), "111"), ["pink"])
        self.assertEqual(await service.owned(str(GUILD_ID), "222"), ["guard"])

    # --- rollback: never take spi without delivering ---

    async def test_role_hierarchy_failure_takes_nothing(self):
        service = self._service(balance=5000)
        member = FakeMember("222", fail_add=True)
        with self.assertRaises(ShopError):
            await service.buy(FakeGuild(), member, "gold")
        self.assertEqual(service.bank.burns, [], "burned spi despite role failure")
        self.assertFalse(await self.repo.owns(str(GUILD_ID), "222", "gold"))

    async def test_burn_failure_rolls_the_role_back(self):
        service = self._service(balance=5000, fail_burn=True)
        guild, member = FakeGuild(), FakeMember("333")
        with self.assertRaises(ShopError):
            await service.buy(guild, member, "vip")
        self.assertEqual(member.removed, [BY_ID["vip"].name], "role not rolled back")
        self.assertFalse(await self.repo.owns(str(GUILD_ID), "333", "vip"))

    async def test_a_failed_rollback_does_not_claim_the_purchase_was_cancelled(self):
        """They kept the role and were not charged - 'cancelled' would be a lie."""
        service = self._service(balance=5000, fail_burn=True)
        guild, member = FakeGuild(), FakeMember("444", fail_remove=True)
        with self.assertRaises(ShopError) as ctx:
            await service.buy(guild, member, "vip")
        self.assertIn("by hand", str(ctx.exception))
        self.assertNotIn("Purchase cancelled", str(ctx.exception))
        self.assertFalse(await self.repo.owns(str(GUILD_ID), "444", "vip"))

    # --- role creation and ordering ---

    async def test_existing_role_is_reused_not_recreated(self):
        service = self._service(balance=9000)
        guild = FakeGuild()
        await service.buy(guild, FakeMember("111"), "pink")
        created = len(guild.roles)
        await service.buy(guild, FakeMember("222"), "pink")
        self.assertEqual(len(guild.roles), created, "second purchase created a duplicate role")

    async def test_cosmetics_outrank_the_arena_roles(self):
        """A buyer holding Player must still see the colour they paid for."""
        service = self._service(balance=9000)
        guild = FakeGuild()
        _, role = await service.buy(guild, FakeMember("111"), "pink")
        player = discord.utils.get(guild.roles, name="Player")
        self.assertGreater(role.position, player.position)
        self.assertLess(role.position, guild.me.top_role.position)

    async def test_most_expensive_owned_cosmetic_wins_the_colour(self):
        service = self._service(balance=9000)
        guild = FakeGuild()
        pink = (await service.buy(guild, FakeMember("111"), "pink"))[1]     # 400
        guard = (await service.buy(guild, FakeMember("222"), "guard"))[1]   # 700
        vip = (await service.buy(guild, FakeMember("333"), "vip"))[1]       # 1500
        self.assertGreater(vip.position, guard.position)
        self.assertGreater(vip.position, pink.position)


if __name__ == "__main__":
    unittest.main()
