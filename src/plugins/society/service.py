"""Society application service - laws, citizenship, treasury, and proposals."""

import uuid
from typing import List, Optional, Tuple

from src.plugins.society.domain import (
    APPROVED,
    CITIZENSHIP_TIERS,
    OPEN,
    REJECTED,
    AlreadyVoted,
    AuthorCannotVote,
    Law,
    NoQuorum,
    Proposal,
    ProposalNotOpen,
    SocietyError,
    tier_for_balance,
    utcnow,
)
from src.plugins.society.repository import SocietyRepository


class SocietyService:
    def __init__(self, repo: SocietyRepository, bank=None):
        self.repo = repo
        self.bank = bank
        self.chronicle = None

    def attach_bank(self, bank) -> None:
        self.bank = bank

    def attach_chronicle(self, chronicle) -> None:
        self.chronicle = chronicle

    # --- Laws ---

    async def add_law(self, guild_id: str, title: str, description: str, fine_amount: int = 0) -> Law:
        law = Law(
            law_id=f"LAW-{uuid.uuid4().hex[:6].upper()}",
            guild_id=guild_id,
            title=title,
            description=description,
            fine_amount=max(0, fine_amount),
            created_at=utcnow(),
        )
        await self.repo.save_law(law)
        if self.chronicle:
            fine = f" (fine {law.fine_amount} spi)" if law.fine_amount else ""
            await self.chronicle.record(
                guild_id, "law_enacted", f"📜 {law.title} was enacted{fine}."
            )
        return law

    async def list_laws(self, guild_id: str) -> List[Law]:
        return await self.repo.list_laws(guild_id)

    async def get_law(self, law_id: str) -> Optional[Law]:
        return await self.repo.get_law(law_id)

    async def remove_law(self, law_id: str) -> None:
        from src.plugins.society.domain import LawNotFound
        law = await self.repo.get_law(law_id)
        if law is None:
            raise LawNotFound(f"No law with ID {law_id}")
        await self.repo.delete_law(law_id)
        if self.chronicle:
            await self.chronicle.record(
                law.guild_id, "law_repealed", f"📜 {law.title} was repealed."
            )

    # --- Proposals ---

    async def propose(self, guild_id: str, author_id: str, title: str, description: str, amount: int = 0) -> Proposal:
        proposal = Proposal(
            proposal_id=f"PROP-{uuid.uuid4().hex[:6].upper()}",
            guild_id=guild_id,
            author_id=author_id,
            title=title,
            description=description,
            amount=max(0, amount),
            status=OPEN,
            approvals="",
            rejections="",
            created_at=utcnow(),
        )
        await self.repo.save_proposal(proposal)
        return proposal

    async def vote(self, guild_id: str, proposal_id: str, voter_id: str, decision: str) -> Proposal:
        proposal = await self.repo.get_proposal(proposal_id)
        if proposal is None:
            from src.plugins.society.domain import ProposalNotFound
            raise ProposalNotFound(f"No proposal with ID {proposal_id}")
        if proposal.status != OPEN:
            raise ProposalNotOpen("That proposal is already closed.")
        if voter_id == proposal.author_id:
            raise AuthorCannotVote("Proposal authors cannot vote on their own proposal.")

        approvers = proposal.approvers()
        rejectors = proposal.rejectors()
        if voter_id in approvers or voter_id in rejectors:
            raise AlreadyVoted("You have already voted on this proposal.")

        if decision == "yes":
            approvers = approvers + [voter_id]
        elif decision == "no":
            rejectors = rejectors + [voter_id]
        else:
            raise SocietyError("Decision must be 'yes' or 'no'.")

        updated = Proposal(
            proposal_id=proposal.proposal_id,
            guild_id=proposal.guild_id,
            author_id=proposal.author_id,
            title=proposal.title,
            description=proposal.description,
            amount=proposal.amount,
            status=proposal.status,
            approvals=",".join(approvers),
            rejections=",".join(rejectors),
            created_at=proposal.created_at,
            resolved_at=proposal.resolved_at,
        )
        await self.repo.update_proposal(updated)
        return updated

    async def conclude(self, guild_id: str, proposal_id: str) -> Proposal:
        proposal = await self.repo.get_proposal(proposal_id)
        if proposal is None:
            from src.plugins.society.domain import ProposalNotFound
            raise ProposalNotFound(f"No proposal with ID {proposal_id}")
        if proposal.status != OPEN:
            raise ProposalNotOpen("That proposal is already concluded.")

        yes = len(proposal.approvers())
        no = len(proposal.rejectors())
        if yes + no == 0:
            raise NoQuorum("No votes cast yet - nothing to conclude.")

        status = APPROVED if yes > no else REJECTED
        updated = Proposal(
            proposal_id=proposal.proposal_id,
            guild_id=proposal.guild_id,
            author_id=proposal.author_id,
            title=proposal.title,
            description=proposal.description,
            amount=proposal.amount,
            status=status,
            approvals=proposal.approvals,
            rejections=proposal.rejections,
            created_at=proposal.created_at,
            resolved_at=utcnow(),
        )
        await self.repo.update_proposal(updated)

        # Payout: approved spending proposals mint from the treasury to the author
        if status == APPROVED and proposal.amount > 0 and self.bank:
            await self.bank.grant(guild_id, proposal.author_id, proposal.amount, f"proposal {proposal_id} approved")

        if self.chronicle:
            verb = "passed" if status == APPROVED else "was rejected"
            payout = (
                f" — {proposal.amount:,} spi released"
                if status == APPROVED and proposal.amount else ""
            )
            await self.chronicle.record(
                guild_id, "proposal_concluded",
                f"🏛️ Proposal `{proposal_id}` “{proposal.title}” {verb} ({yes}–{no}){payout}.",
            )

        return updated

    async def list_proposals(self, guild_id: str, status: Optional[str] = None) -> List[Proposal]:
        return await self.repo.list_proposals(guild_id, status)

    # --- Treasury & Citizenship ---

    async def treasury_balance(self, guild_id: str) -> int:
        if not self.bank:
            return 0
        return await self.bank.treasury_balance(guild_id)

    async def get_tax_rate(self, guild_id: str) -> int:
        if not self.bank:
            return 0
        return await self.bank.get_tax_rate(guild_id)

    async def set_tax_rate(self, guild_id: str, rate_bps: int) -> int:
        if not self.bank:
            from src.plugins.society.domain import SocietyError
            raise SocietyError("Bank is not available.")
        return await self.bank.set_tax_rate(guild_id, rate_bps)

    async def citizenship(self, guild_id: str, user_id: str) -> Tuple[int, str, int, str]:
        if not self.bank:
            return 0, "Resident", 0, ""
        await self.bank.ensure_account(guild_id, user_id)
        balance = await self.bank.balance(guild_id, user_id)
        title, threshold = tier_for_balance(balance)
        next_title = ""
        for t, th in CITIZENSHIP_TIERS:
            if th > threshold:
                next_title = f"{t} @ {th} spi"
                break
        return balance, title, threshold, next_title
