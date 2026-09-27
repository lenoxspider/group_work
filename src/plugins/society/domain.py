"""Society domain - laws, proposals, citizenship tiers, and errors."""

from dataclasses import dataclass, field
from datetime import datetime, timezone

OPEN = "OPEN"
APPROVED = "APPROVED"
REJECTED = "REJECTED"


class SocietyError(Exception):
    """Base society domain error."""


class LawNotFound(SocietyError):
    pass


class ProposalNotFound(SocietyError):
    pass


class ProposalNotOpen(SocietyError):
    pass


class AuthorCannotVote(SocietyError):
    pass


class AlreadyVoted(SocietyError):
    pass


class NoQuorum(SocietyError):
    pass


# Net-worth citizenship tiers: (title, minimum spi balance)
CITIZENSHIP_TIERS = [
    ("Resident", 0),
    ("Citizen", 250),
    ("Merchant", 1000),
    ("Magnate", 5000),
    ("Oligarch", 25000),
]


def tier_for_balance(balance: int):
    """Return the (title, threshold) of the highest tier the balance qualifies for."""
    current = CITIZENSHIP_TIERS[0]
    for title, threshold in CITIZENSHIP_TIERS:
        if balance >= threshold:
            current = (title, threshold)
    return current


@dataclass(frozen=True)
class Law:
    law_id: str
    guild_id: str
    title: str
    description: str
    fine_amount: int
    created_at: str


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    guild_id: str
    author_id: str
    title: str
    description: str
    amount: int
    status: str
    approvals: str
    rejections: str
    created_at: str
    resolved_at: str = ""

    def approvers(self) -> list:
        return [u for u in self.approvals.split(",") if u]

    def rejectors(self) -> list:
        return [u for u in self.rejections.split(",") if u]


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")