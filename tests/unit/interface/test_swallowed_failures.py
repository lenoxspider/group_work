"""Tests for failures the cog layer used to swallow.

Every one of these told a citizen something untrue, or lost an action they had
taken, because an exception was caught and discarded:

- a failed balance read reported as "0 spi" - an outage rendered as poverty
- a failed mark read re-offering the mark picker, implying the choice was lost
- any failure while recording a court vote diagnosed as "ineligible voter" and
  the juror's reaction stripped, destroying a legitimate vote and its evidence
- an appeal that promised "fresh jury, fresh vote" with no card and no reactions
- a reminder recorded as delivered when the send failed, suppressing it forever

Swallowing is often the right call: a cosmetic announcement failing after the
state has committed must not fail the command, because the member did complete
the task and was paid. What a swallow must never do is change what the user is
told about something that did not happen. Each test here pins that line, and
each is paired with the opposite case so the fix cannot quietly over-correct -
a genuine zero balance must still read as zero, and a genuinely unset mark must
still offer the picker.
"""

import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.domain.errors import ValidationError
from src.plugins.community.cog import GUILTY_EMOJI, INNOCENT_EMOJI, CommunityCog
from src.plugins.community.domain import CITIZEN, Case
from src.plugins.community.intro import MarkChooserView
from src.plugins.shop.cog import ShopCog
from src.interface.cogs.task_reminder_cog import TaskReminderCog

GUILD_ID = 999
USER_ID = 4242


def _interaction():
    interaction = AsyncMock()
    interaction.guild_id = GUILD_ID
    interaction.user.id = USER_ID
    interaction.user.display_name = "Comrade"
    interaction.response = AsyncMock()
    interaction.followup = AsyncMock()
    return interaction


def _bank(value):
    """A fake bank whose balance() returns value, or raises it if it is an error."""
    async def balance(guild_id, user_id):
        if isinstance(value, Exception):
            raise value
        return value
    return SimpleNamespace(balance=balance)


class TestShopBalanceReporting(unittest.IsolatedAsyncioTestCase):
    def _cog(self, balance):
        cog = object.__new__(ShopCog)
        cog.service = SimpleNamespace(
            bank=_bank(balance),
            owned=AsyncMock(return_value=[]),
            total_burned=AsyncMock(return_value=0),
        )
        cog.bot = SimpleNamespace()
        return cog

    def _description(self, interaction):
        return interaction.followup.send.call_args.kwargs["embed"].description

    async def test_a_failed_read_is_not_reported_as_poverty(self):
        cog = self._cog(RuntimeError("database is locked"))
        interaction = _interaction()
        await cog.shop_view.callback(cog, interaction)
        text = self._description(interaction)
        self.assertNotIn("0 spi", text)
        self.assertIn("could not be read", text)

    async def test_a_genuine_zero_is_still_reported_as_zero(self):
        """Three citizens really do hold 0 spi; the guard must not hide that."""
        cog = self._cog(0)
        interaction = _interaction()
        await cog.shop_view.callback(cog, interaction)
        self.assertIn("You hold **0 spi**", self._description(interaction))

    async def test_a_readable_balance_is_shown(self):
        cog = self._cog(3150)
        interaction = _interaction()
        await cog.shop_view.callback(cog, interaction)
        self.assertIn("3,150 spi", self._description(interaction))


class TestPassportMeReporting(unittest.IsolatedAsyncioTestCase):
    def _cog(self, balance, mark, mark_raises=False):
        cog = object.__new__(CommunityCog)
        seen = {}
        member = SimpleNamespace(
            status=CITIZEN, intro_done=True, intro_task_id=None,
            signed_at="2026-09-28T15:54:37+00:00",
        )

        async def get_mark(guild_id, user_id):
            if mark_raises:
                raise RuntimeError("database is locked")
            return mark

        cog.service = SimpleNamespace(
            get_member=AsyncMock(return_value=member),
            get_mark=get_mark,
            bank=_bank(balance),
        )

        async def render(interaction, mem, bal, citizen_no, mk=None):
            seen["balance"] = bal
            seen["mark"] = mk
            return None  # force the text card, which is what we assert against

        cog._render_passport = render
        cog.bot = SimpleNamespace(settings=SimpleNamespace(guild_id=None), guilds=[])
        return cog, seen

    def _wallet(self, interaction):
        embed = interaction.followup.send.call_args.kwargs["embed"]
        for field in embed.fields:
            if field.name == "Wallet":
                return field.value
        self.fail("the passport has no Wallet field")

    async def test_a_failed_balance_read_is_not_rendered_as_zero(self):
        cog, seen = self._cog(RuntimeError("database is locked"), mark="○ Circle")
        interaction = _interaction()
        await cog.me.callback(cog, interaction)
        self.assertIsNone(seen["balance"])
        self.assertNotIn("0 spi", self._wallet(interaction))

    async def test_a_failed_mark_read_does_not_offer_the_picker(self):
        """A load failure is not evidence that the member never chose a mark."""
        cog, _ = self._cog(3150, mark=None, mark_raises=True)
        interaction = _interaction()
        await cog.me.callback(cog, interaction)
        view = interaction.followup.send.call_args.kwargs.get("view")
        self.assertNotIsInstance(view, MarkChooserView)

    async def test_a_genuinely_unset_mark_still_offers_the_picker(self):
        cog, _ = self._cog(3150, mark=None, mark_raises=False)
        interaction = _interaction()
        await cog.me.callback(cog, interaction)
        view = interaction.followup.send.call_args.kwargs.get("view")
        self.assertIsInstance(view, MarkChooserView)

    async def test_a_recorded_mark_gets_a_clean_passport(self):
        cog, seen = self._cog(3150, mark="△ Triangle")
        interaction = _interaction()
        await cog.me.callback(cog, interaction)
        self.assertEqual(seen["mark"], "△ Triangle")
        self.assertIsNone(interaction.followup.send.call_args.kwargs.get("view"))


class TestCourtVoteReaction(unittest.IsolatedAsyncioTestCase):
    def _cog(self, error):
        cog = object.__new__(CommunityCog)
        stripped = []
        case = Case(
            case_id="CASE-1", guild_id=str(GUILD_ID),
            accuser_id="1", accused_id="2", law_id="LAW-1",
        )

        async def court_vote(guild_id, case_id, voter_id, decision):
            raise error

        cog.service = SimpleNamespace(
            get_case_by_message=AsyncMock(return_value=case),
            court_vote=court_vote,
        )

        class FakeMessage:
            async def remove_reaction(self, emoji, user):
                stripped.append((str(emoji), user.id))

        class FakeChannel:
            async def fetch_message(self, message_id):
                return FakeMessage()

        cog.bot = SimpleNamespace(
            user=SimpleNamespace(id=1),
            get_channel=lambda channel_id: FakeChannel(),
        )
        return cog, stripped

    def _payload(self):
        return SimpleNamespace(
            guild_id=GUILD_ID, user_id=USER_ID, emoji=GUILTY_EMOJI,
            message_id=555, channel_id=777,
        )

    async def test_an_ineligible_voter_has_their_reaction_stripped(self):
        cog, stripped = self._cog(ValidationError("Only citizens sit on the jury."))
        await cog.on_raw_reaction_add(self._payload())
        self.assertEqual(stripped, [(GUILTY_EMOJI, USER_ID)])

    async def test_an_unexpected_failure_preserves_the_vote(self):
        """A storage error is our fault, not proof the juror was ineligible.

        Stripping here destroyed a legitimate vote and removed the only evidence
        it was ever cast, while the log stayed silent about both.
        """
        cog, stripped = self._cog(RuntimeError("database is locked"))
        await cog.on_raw_reaction_add(self._payload())
        self.assertEqual(stripped, [])


class TestCourtAppeal(unittest.IsolatedAsyncioTestCase):
    def _cog(self, card_fails):
        cog = object.__new__(CommunityCog)
        reactions = []
        case = Case(
            case_id="CASE-1", guild_id=str(GUILD_ID),
            accuser_id="1", accused_id="2", law_id="LAW-1",
        )

        class FakeCard:
            id = 555

            async def add_reaction(self, emoji):
                reactions.append(str(emoji))

        class FakeTribunal:
            id = 777

            async def send(self, **kwargs):
                if card_fails:
                    raise RuntimeError("Missing Permissions")
                return FakeCard()

        cog.service = SimpleNamespace(
            appeal_case=AsyncMock(return_value=case),
            repo=SimpleNamespace(save_case=AsyncMock()),
        )
        cog._refresh_case_card = AsyncMock()
        cog._tribunal_channel = AsyncMock(return_value=FakeTribunal())
        cog._law = AsyncMock(return_value=SimpleNamespace(title="Test Law", fine_amount=100))
        return cog, reactions, case

    async def test_a_failed_card_does_not_promise_a_fresh_jury(self):
        cog, reactions, case = self._cog(card_fails=True)
        interaction = _interaction()
        await cog.court_appeal.callback(cog, interaction, case_id="CASE-1")
        text = interaction.followup.send.call_args[0][0]
        self.assertNotIn("Fresh jury", text)
        self.assertIn("could not be posted", text)
        self.assertIn("/court vote", text)
        self.assertEqual(reactions, [])

    async def test_the_appeal_is_still_granted_when_the_card_fails(self):
        """The reopening happens in appeal_case(); a broken card must not read as
        a refused appeal."""
        cog, _, case = self._cog(card_fails=True)
        interaction = _interaction()
        await cog.court_appeal.callback(cog, interaction, case_id="CASE-1")
        self.assertIn("Appeal granted", interaction.followup.send.call_args[0][0])

    async def test_a_posted_card_convenes_the_jury(self):
        cog, reactions, case = self._cog(card_fails=False)
        interaction = _interaction()
        await cog.court_appeal.callback(cog, interaction, case_id="CASE-1")
        self.assertIn("Fresh jury, fresh vote", interaction.followup.send.call_args[0][0])
        self.assertEqual(reactions, [GUILTY_EMOJI, INNOCENT_EMOJI])
        self.assertEqual(case.message_id, "555")


class TestReminderIsNotMarkedDeliveredOnFailure(unittest.IsolatedAsyncioTestCase):
    def _cog(self, send_fails):
        cog = object.__new__(TaskReminderCog)
        calls = {"fired": [], "acknowledged": [], "sent": 0}
        due = datetime.now(timezone.utc) + timedelta(hours=20)
        action = SimpleNamespace(
            reminder_tier="24h", task_id="TASK-1", guild_id=str(GUILD_ID),
            user_id=str(USER_ID), description="Write the report", due_date=due,
        )

        class FakeUser:
            display_name = "Comrade"

            async def send(self, **kwargs):
                calls["sent"] += 1
                if send_fails:
                    raise RuntimeError("Cannot send messages to this user")

        class FakeAlertRepo:
            async def has_fired(self, task_id, alert_tier):
                return False

            async def record_fire(self, fire):
                calls["fired"].append((fire.task_id, fire.alert_tier))
                return True

        async def acknowledge(task_id, tier):
            calls["acknowledged"].append((task_id, tier))

        cog.service = SimpleNamespace(
            evaluate_pending_reminders=AsyncMock(return_value=[action]),
            acknowledge_reminder=acknowledge,
        )
        cog.alert_fire_repo = FakeAlertRepo()
        cog.preference_service = None
        cog.voice_service = None
        cog.channel_router = None
        cog.bot = SimpleNamespace(get_user=lambda uid: FakeUser())
        cog._dispatch_wall_of_shame = AsyncMock()
        return cog, calls

    async def test_a_failed_dm_is_left_for_retry(self):
        """Recording the fire before delivery suppressed the reminder permanently:
        both alert_fires and acknowledge_reminder then reported a tier as fired
        that the member was never told about."""
        cog, calls = self._cog(send_fails=True)
        await cog.reminder_loop.coro(cog)
        self.assertEqual(calls["sent"], 1)
        self.assertEqual(calls["fired"], [])
        self.assertEqual(calls["acknowledged"], [])

    async def test_a_delivered_dm_is_recorded_and_acknowledged(self):
        cog, calls = self._cog(send_fails=False)
        await cog.reminder_loop.coro(cog)
        self.assertEqual(calls["sent"], 1)
        self.assertEqual(calls["fired"], [("TASK-1", "24h")])
        self.assertEqual(calls["acknowledged"], [("TASK-1", "24h")])


if __name__ == "__main__":
    unittest.main()
