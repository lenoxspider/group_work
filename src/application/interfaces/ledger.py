"""
Ledger port - the minimal money contract an application service needs.

The bank plugin's BankService structurally satisfies this Protocol
(grant / burn), so the groupwork plugin can inject it without the shared
task service importing any plugin code.
"""

from typing import Protocol


class Ledger(Protocol):
    """Mint or burn spi on behalf of a guild member."""

    async def grant(self, guild_id: str, user_id: str, amount: int, reason: str = "") -> object:
        """Mint spi from the treasury into an account."""
        ...

    async def burn(self, guild_id: str, user_id: str, amount: int, reason: str = "") -> object:
        """Remove spi from circulation into the sink."""
        ...