"""Tests for office role reconciliation.

The database is the source of truth; the Discord role is only its visible
marker. These pin both directions - a holder missing the role gets it, a
non-holder wearing it loses it - plus the cases that must not blow up: roles
/setup has not created yet, bots, and a member the bot cannot manage.
"""

import unittest
from types import SimpleNamespace

import discord

from src.plugins.offices.cog import OfficesCog
from src.plugins.offices.domain import FRONT_MAN, MAGISTRATE, TREASURER


class FakeRole:
    def __init__(self, name):
        self.name = name


class FakeMember:
    def __init__(self, user_id, roles=(), bot=False, fail=False):
        self.id = int(user_id)
        self.bot = bot
        self.roles = list(roles)
        self.fail = fail
        self.added = []
        self.removed = []

    async def add_roles(self, role, reason=None):
        if self.fail:
            raise RuntimeError("role hierarchy")
        self.roles.append(role)
        self.added.append(role.name)

    async def remove_roles(self, role, reason=None):
        if self.fail:
            raise RuntimeError("role hierarchy")
        self.roles.remove(role)
        self.removed.append(role.name)


class FakeGuild:
    def __init__(self, members, with_roles=True):
        self.id = 1553052975876939876
        self.roles = [FakeRole(n) for n in ("Magistrate", "Treasurer", "Front Man")] if with_roles else []
        self.members = members


class FakeService:
    def __init__(self, holders):
        self.holders = holders

    async def holder(self, guild_id, office):
        return self.holders.get(office)


def _cog(holders):
    cog = object.__new__(OfficesCog)
    cog.service = FakeService(holders)
    cog.bot = SimpleNamespace(guilds=[])
    return cog


def _role(guild, name):
    return discord.utils.get(guild.roles, name=name)


class TestOfficeReconcile(unittest.IsolatedAsyncioTestCase):
    async def test_a_holder_missing_the_role_receives_it(self):
        guild = FakeGuild([FakeMember("111")])
        await _cog({MAGISTRATE: "111"}).reconcile_office_roles(guild)
        self.assertEqual(guild.members[0].added, ["Magistrate"])

    async def test_a_non_holder_wearing_the_role_loses_it(self):
        guild = FakeGuild([FakeMember("111")])
        stale = _role(guild, "Treasurer")
        guild.members[0].roles.append(stale)
        await _cog({}).reconcile_office_roles(guild)
        self.assertEqual(guild.members[0].removed, ["Treasurer"])

    async def test_a_correct_member_is_left_untouched(self):
        guild = FakeGuild([FakeMember("111")])
        guild.members[0].roles.append(_role(guild, "Magistrate"))
        await _cog({MAGISTRATE: "111"}).reconcile_office_roles(guild)
        self.assertEqual(guild.members[0].added, [])
        self.assertEqual(guild.members[0].removed, [])

    async def test_one_member_can_hold_several_offices(self):
        guild = FakeGuild([FakeMember("111")])
        await _cog({MAGISTRATE: "111", FRONT_MAN: "111"}).reconcile_office_roles(guild)
        self.assertEqual(sorted(guild.members[0].added), ["Front Man", "Magistrate"])

    async def test_an_office_handing_over_moves_the_role(self):
        guild = FakeGuild([FakeMember("111"), FakeMember("222")])
        guild.members[0].roles.append(_role(guild, "Magistrate"))
        await _cog({MAGISTRATE: "222"}).reconcile_office_roles(guild)
        self.assertEqual(guild.members[0].removed, ["Magistrate"])
        self.assertEqual(guild.members[1].added, ["Magistrate"])

    async def test_bots_are_skipped(self):
        guild = FakeGuild([FakeMember("999", bot=True)])
        await _cog({MAGISTRATE: "999"}).reconcile_office_roles(guild)
        self.assertEqual(guild.members[0].added, [])

    async def test_missing_roles_are_a_noop_not_a_crash(self):
        """/setup has not run yet, so none of the office roles exist."""
        guild = FakeGuild([FakeMember("111")], with_roles=False)
        await _cog({MAGISTRATE: "111"}).reconcile_office_roles(guild)
        self.assertEqual(guild.members[0].added, [])

    async def test_an_unmanageable_member_does_not_abort_the_others(self):
        stuck = FakeMember("111", fail=True)
        fine = FakeMember("222")
        guild = FakeGuild([stuck, fine])
        await _cog({MAGISTRATE: "111", TREASURER: "222"}).reconcile_office_roles(guild)
        self.assertEqual(fine.added, ["Treasurer"], "one failure must not stop the rest")


if __name__ == "__main__":
    unittest.main()
