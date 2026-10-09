"""Tests for the ○ △ □ mark chooser.

The mark is asked during the introduction but was only persisted from a certain
point on, so members who introduced themselves earlier have none and their
passport shows a dash. The chooser lets them claim it. These pin the button ids
(persistent views are matched by custom_id across restarts) and that a click
records the mark for the person who clicked.
"""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.plugins.community.cog import CommunityCog
from src.plugins.community.intro import MarkChooserView


class TestMarkChooserView(unittest.TestCase):
    def test_the_three_marks_have_stable_custom_ids(self):
        view = MarkChooserView(None)
        self.assertEqual(
            sorted(c.custom_id for c in view.children),
            ["mark:circle", "mark:square", "mark:triangle"],
        )

    def test_the_view_is_persistent(self):
        self.assertIsNone(MarkChooserView(None).timeout)


class TestSetMarkFromButton(unittest.IsolatedAsyncioTestCase):
    def _cog(self, recorded):
        cog = object.__new__(CommunityCog)

        class FakeService:
            async def set_mark(self, guild_id, user_id, mark):
                recorded["args"] = (guild_id, user_id, mark)

        cog.service = FakeService()
        cog.bot = SimpleNamespace(settings=SimpleNamespace(guild_id=None), guilds=[])
        return cog

    def _interaction(self, guild_id=999, user_id=4242):
        interaction = AsyncMock()
        interaction.guild_id = guild_id
        interaction.user.id = user_id
        interaction.response = AsyncMock()
        interaction.followup = AsyncMock()
        return interaction

    async def test_click_records_the_mark_for_the_clicker(self):
        recorded = {}
        cog = self._cog(recorded)
        interaction = self._interaction()
        await cog.set_mark_from_button(interaction, "△ Triangle")
        self.assertEqual(recorded["args"], ("999", "4242", "△ Triangle"))
        interaction.response.defer.assert_awaited_once_with(ephemeral=True)
        interaction.followup.send.assert_awaited()

    async def test_a_failure_tells_the_user_rather_than_hanging(self):
        cog = self._cog({})

        async def boom(*args, **kwargs):
            raise RuntimeError("db locked")

        cog.service.set_mark = boom
        interaction = self._interaction()
        await cog.set_mark_from_button(interaction, "○ Circle")
        interaction.followup.send.assert_awaited()
        self.assertIn("Could not record", interaction.followup.send.call_args[0][0])


if __name__ == "__main__":
    unittest.main()
