"""Bank application service - orchestration over the repository."""

from src.plugins.bank.domain import SINK, TREASURY, Transaction
from src.plugins.bank.repository import SQLiteBankRepository


class BankService:
    def __init__(self, repo: SQLiteBankRepository):
        self.repo = repo

    async def balance(self, guild_id: str, user_id: str) -> int:
        return await self.repo.get_balance(guild_id, user_id)

    async def ensure_account(self, guild_id: str, user_id: str) -> None:
        await self.repo.ensure_account(guild_id, user_id)

    async def transfer(
        self, guild_id: str, from_user: str, to_user: str, amount: int, reason: str = ""
    ) -> Transaction:
        return await self.repo.transfer(guild_id, from_user, to_user, amount, reason)

    async def grant(self, guild_id: str, user_id: str, amount: int, reason: str = "") -> Transaction:
        """Mint spi from the treasury faucet into an account."""
        return await self.repo.transfer(guild_id, TREASURY, user_id, amount, reason)

    async def burn(self, guild_id: str, user_id: str, amount: int, reason: str = "") -> Transaction:
        """Remove spi from circulation into the sink."""
        return await self.repo.transfer(guild_id, user_id, SINK, amount, reason)

    async def ledger(self, guild_id: str, user_id: str, limit: int = 20) -> list[Transaction]:
        return await self.repo.ledger(guild_id, user_id, limit)