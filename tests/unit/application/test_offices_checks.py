"""Tests for the office gate.

The behaviour that matters: an office holder passes, an admin passes as a
fallback (so an empty seat never locks the founder out), a plain citizen does
not, and a missing offices plugin fails open rather than breaking every command
that depends on it.
"""

import unittest
from types import SimpleNamespace

from src.plugins.offices.checks import holds_office_or_admin
from src.plugins.offices.domain import MAGISTRATE


class FakeOfficesService:
    def __init__(self, holders):
        self.holders = holders

    async def holds(self, guild_id, user_id, office):
        return self.holders.get((guild_id, user_id, office), False)


def _interaction(plugins, manage_guild=False, guild_id=1, user_id=42):
    return SimpleNamespace(
        client=SimpleNamespace(plugins=plugins),
        guild_id=guild_id,
        user=SimpleNamespace(id=user_id),
        permissions=SimpleNamespace(manage_guild=manage_guild),
    )


def _offices_plugin(holders):
    return {"offices": SimpleNamespace(service=FakeOfficesService(holders))}


class TestHoldsOfficeOrAdmin(unittest.IsolatedAsyncioTestCase):
    async def test_the_office_holder_passes(self):
        plugins = _offices_plugin({("1", "42", MAGISTRATE): True})
        self.assertTrue(await holds_office_or_admin(_interaction(plugins), MAGISTRATE))

    async def test_an_admin_passes_as_a_fallback(self):
        """An empty seat must not lock the founder out of their own court."""
        plugins = _offices_plugin({})
        interaction = _interaction(plugins, manage_guild=True)
        self.assertTrue(await holds_office_or_admin(interaction, MAGISTRATE))

    async def test_a_plain_citizen_does_not_pass(self):
        plugins = _offices_plugin({})
        interaction = _interaction(plugins, manage_guild=False)
        self.assertFalse(await holds_office_or_admin(interaction, MAGISTRATE))

    async def test_a_missing_offices_plugin_fails_open(self):
        self.assertTrue(await holds_office_or_admin(_interaction({}), MAGISTRATE))

    async def test_no_guild_means_no_office(self):
        plugins = _offices_plugin({("1", "42", MAGISTRATE): True})
        interaction = _interaction(plugins, guild_id=None)
        self.assertFalse(await holds_office_or_admin(interaction, MAGISTRATE))

    async def test_holding_a_different_office_does_not_pass(self):
        from src.plugins.offices.domain import TREASURER
        plugins = _offices_plugin({("1", "42", TREASURER): True})
        self.assertFalse(
            await holds_office_or_admin(_interaction(plugins, manage_guild=False), MAGISTRATE)
        )


if __name__ == "__main__":
    unittest.main()
