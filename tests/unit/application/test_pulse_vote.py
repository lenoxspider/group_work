"""Unit tests for Snap Trial vote resolution.

This is the pulse mode that moves real spi: a guilty verdict fines the accused
into the treasury, an innocent one pays them compensation out of it. It was
originally verified with a throwaway script that was deleted afterwards, so the
money path had no coverage.

The tally rules matter because they decide who pays:
- bots, the accused, and non-citizens are filtered out
- a voter who clicks both verdicts cancels themselves out
- no valid votes means the case is dismissed and nothing moves
- a tie acquits
"""

import unittest

from src.plugins.bank.domain import TREASURY, InsufficientFunds
from src.plugins.pulse.domain import (
    SNAP_COMPENSATION_SPI,
    SNAP_FINE_SPI,
    SNAP_GUILTY_EMOJI,
    SNAP_INNOCENT_EMOJI,
    ActivePulse,
    utcnow,
)
from src.plugins.pulse.service import PulseService

GUILD = "guild-snap"
ACCUSED = "111"


class FakeUser:
    def __init__(self, user_id, bot=False):
        self.id = int(user_id)
        self.bot = bot


class FakeReaction:
    def __init__(self, emoji, users):
        self.emoji = emoji
        self._users = users

    def users(self):
        async def generate():
            for user in self._users:
                yield user

        return generate()


class FakeMessage:
    def __init__(self, reactions):
        self.reactions = reactions


class FakeCommunity:
    def __init__(self, citizens):
        self._citizens = set(citizens)

    async def is_citizen(self, guild_id, user_id):
        return user_id in self._citizens


class FakeBank:
    def __init__(self, fail_transfer=False, error=None, fail_grant=False):
        self.fail_transfer = fail_transfer
        self.error = error if error is not None else InsufficientFunds("holds 0 spi, attempted 50")
        self.fail_grant = fail_grant
        self.transfers = []
        self.grants = []

    async def transfer(self, guild_id, from_user, to_user, amount, reason=""):
        if self.fail_transfer:
            raise self.error
        self.transfers.append((from_user, to_user, amount, reason))

    async def grant(self, guild_id, user_id, amount, reason=""):
        if self.fail_grant:
            raise RuntimeError("treasury unreachable")
        self.grants.append((user_id, amount, reason))


def _pulse(accused=ACCUSED, crime="testing"):
    return ActivePulse(
        guild_id=GUILD, channel_id="c1", message_id="m1",
        kind="snap_trial", label="Snap Trial", answer="", mode="vote",
        started_at=utcnow(),
        vote_options={SNAP_GUILTY_EMOJI: "guilty", SNAP_INNOCENT_EMOJI: "innocent"},
        data={"accused_id": accused, "crime": crime},
    )


def _message(guilty=(), innocent=()):
    return FakeMessage([
        FakeReaction(SNAP_GUILTY_EMOJI, list(guilty)),
        FakeReaction(SNAP_INNOCENT_EMOJI, list(innocent)),
    ])


def _service(citizens=("111", "222", "333"), bank=None):
    service = PulseService(repo=None)
    service.attach_bank(bank if bank is not None else FakeBank())
    service.attach_community(FakeCommunity(citizens))
    return service


class TestSnapTrialTally(unittest.IsolatedAsyncioTestCase):
    async def test_counts_only_eligible_voters(self):
        service = _service()
        message = _message(
            guilty=[FakeUser("222"), FakeUser("333")],
            innocent=[FakeUser("999", bot=True)],
        )
        counts = await service._tally(_pulse(), message)
        self.assertEqual(counts[SNAP_GUILTY_EMOJI], 2)
        self.assertEqual(counts[SNAP_INNOCENT_EMOJI], 0)

    async def test_the_accused_cannot_vote_on_their_own_trial(self):
        service = _service()
        message = _message(guilty=[FakeUser(ACCUSED), FakeUser("222")])
        counts = await service._tally(_pulse(), message)
        self.assertEqual(counts[SNAP_GUILTY_EMOJI], 1)

    async def test_non_citizens_are_excluded_from_the_jury(self):
        service = _service(citizens=("111", "222"))
        message = _message(guilty=[FakeUser("222"), FakeUser("777")])
        counts = await service._tally(_pulse(), message)
        self.assertEqual(counts[SNAP_GUILTY_EMOJI], 1)

    async def test_voting_both_ways_cancels_the_vote(self):
        service = _service()
        message = _message(
            guilty=[FakeUser("222"), FakeUser("333")],
            innocent=[FakeUser("222")],
        )
        counts = await service._tally(_pulse(), message)
        self.assertEqual(counts[SNAP_GUILTY_EMOJI], 1, "double voter should not count")
        self.assertEqual(counts[SNAP_INNOCENT_EMOJI], 0)

    async def test_unknown_emoji_is_ignored(self):
        service = _service()
        message = FakeMessage([
            FakeReaction("🎉", [FakeUser("222")]),
            FakeReaction(SNAP_GUILTY_EMOJI, [FakeUser("333")]),
        ])
        counts = await service._tally(_pulse(), message)
        self.assertEqual(counts[SNAP_GUILTY_EMOJI], 1)
        self.assertEqual(set(counts), {SNAP_GUILTY_EMOJI, SNAP_INNOCENT_EMOJI})


class TestSnapTrialVerdict(unittest.IsolatedAsyncioTestCase):
    async def test_guilty_fines_the_accused_into_the_treasury(self):
        bank = FakeBank()
        service = _service(bank=bank)
        result = await service.resolve_vote(
            _pulse(), _message(guilty=[FakeUser("222"), FakeUser("333")])
        )
        self.assertEqual(result["verdict"], "guilty")
        self.assertEqual(
            bank.transfers, [(ACCUSED, TREASURY, SNAP_FINE_SPI, "snap trial fine")]
        )
        self.assertEqual(bank.grants, [])

    async def test_innocent_pays_the_accused_compensation(self):
        bank = FakeBank()
        service = _service(bank=bank)
        result = await service.resolve_vote(
            _pulse(), _message(innocent=[FakeUser("222"), FakeUser("333")])
        )
        self.assertEqual(result["verdict"], "innocent")
        self.assertEqual(
            bank.grants, [(ACCUSED, SNAP_COMPENSATION_SPI, "snap trial compensation")]
        )
        self.assertEqual(bank.transfers, [])

    async def test_a_tie_acquits(self):
        bank = FakeBank()
        service = _service(bank=bank)
        result = await service.resolve_vote(
            _pulse(), _message(guilty=[FakeUser("222")], innocent=[FakeUser("333")])
        )
        self.assertEqual(result["verdict"], "innocent")
        self.assertEqual(bank.transfers, [], "a tie must not fine anyone")

    async def test_no_valid_votes_moves_nothing(self):
        bank = FakeBank()
        service = _service(bank=bank)
        result = await service.resolve_vote(_pulse(), _message())
        self.assertEqual(result["verdict"], "silent")
        self.assertEqual(bank.transfers, [])
        self.assertEqual(bank.grants, [])

    async def test_bot_only_votes_count_as_silence(self):
        bank = FakeBank()
        service = _service(bank=bank)
        result = await service.resolve_vote(
            _pulse(), _message(guilty=[FakeUser("999", bot=True)])
        )
        self.assertEqual(result["verdict"], "silent")
        self.assertEqual(bank.transfers, [])

    async def test_a_broke_convict_is_shamed_not_crashed(self):
        bank = FakeBank(fail_transfer=True)
        service = _service(bank=bank)
        result = await service.resolve_vote(
            _pulse(), _message(guilty=[FakeUser("222"), FakeUser("333")])
        )
        self.assertEqual(result["verdict"], "guilty_broke")
        self.assertIn("broke", result["text"])

    async def test_a_ledger_failure_is_not_reported_as_the_member_being_broke(self):
        """Calling someone broke when the bank merely failed is a false public
        statement about them, so a technical error gets its own verdict."""
        bank = FakeBank(fail_transfer=True, error=RuntimeError("database is locked"))
        service = _service(bank=bank)
        result = await service.resolve_vote(
            _pulse(), _message(guilty=[FakeUser("222"), FakeUser("333")])
        )
        self.assertEqual(result["verdict"], "guilty_unpaid")
        self.assertNotIn("broke", result["text"])
        self.assertIn("could not be collected", result["text"])

    async def test_a_failed_compensation_still_acquits(self):
        bank = FakeBank(fail_grant=True)
        service = _service(bank=bank)
        result = await service.resolve_vote(
            _pulse(), _message(innocent=[FakeUser("222"), FakeUser("333")])
        )
        self.assertEqual(result["verdict"], "innocent")
        self.assertEqual(bank.grants, [])

    async def test_verdict_text_names_the_accused_and_the_tally(self):
        service = _service()
        result = await service.resolve_vote(
            _pulse(crime="hoarding bread"),
            _message(guilty=[FakeUser("222"), FakeUser("333")]),
        )
        self.assertIn(f"<@{ACCUSED}>", result["text"])
        self.assertIn("hoarding bread", result["text"])
        self.assertIn("2", result["text"])

    async def test_no_bank_still_returns_a_verdict(self):
        service = _service()
        service.attach_bank(None)
        result = await service.resolve_vote(
            _pulse(), _message(guilty=[FakeUser("222")])
        )
        self.assertEqual(result["verdict"], "guilty")

    async def test_a_single_vote_decides(self):
        """No quorum is required, which on a five-person server is deliberate."""
        bank = FakeBank()
        service = _service(bank=bank)
        result = await service.resolve_vote(_pulse(), _message(guilty=[FakeUser("222")]))
        self.assertEqual(result["verdict"], "guilty")
        self.assertEqual(len(bank.transfers), 1)


if __name__ == "__main__":
    unittest.main()
