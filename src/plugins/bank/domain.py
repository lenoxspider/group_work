"""Bank domain - spi currency, accounts, and virtual money faucets/sinks."""

from dataclasses import dataclass
from datetime import datetime, timezone

TREASURY = "__treasury__"
SINK = "__sink__"


class BankError(Exception):
    """Base bank domain error."""


class InsufficientFunds(BankError):
    """Sender does not hold enough spi."""


class InvalidAmount(BankError):
    """Transfer amount must be a positive integer."""


class SelfTransfer(BankError):
    """Accounts cannot transfer spi to themselves."""


@dataclass(frozen=True)
class Transaction:
    tx_id: str
    guild_id: str
    from_user: str
    to_user: str
    amount: int
    reason: str
    created_at: str


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")