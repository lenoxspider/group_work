"""Bank application service - orchestration over the repository."""

from src.plugins.bank.domain import SINK, TREASURY, Transaction
from src.plugins.bank.repository import SQLiteBankRepository


class BankService:
    def __init__(self, repo: SQLiteBankRepository):
        self.repo = repo

    async def balance(self, guild_id: str, user_id: str) -> int:
        return await self.repo.get_balance(guild_id, user_id)

    async def treasury_balance(self, guild_id: str) -> int:
        """Net minted supply (negative when spi has been printed into circulation)."""
        return await self.repo.get_balance(guild_id, TREASURY)

    async def ensure_account(self, guild_id: str, user_id: str) -> None:
        await self.repo.ensure_account(guild_id, user_id)

    async def get_tax_rate(self, guild_id: str) -> int:
        """Current transfer tax rate in basis points (250 = 2.5%)."""
        return await self.repo.get_tax_rate(guild_id)

    async def set_tax_rate(self, guild_id: str, rate_bps: int) -> int:
        """Set the transfer tax rate in basis points. 0 disables taxation."""
        if rate_bps < 0 or rate_bps > 10000:
            raise ValueError("tax rate must be between 0 and 10000 basis points (0% to 100%)")
        await self.repo.set_tax_rate(guild_id, rate_bps)
        return rate_bps

    async def transfer(
        self, guild_id: str, from_user: str, to_user: str, amount: int, reason: str = ""
    ) -> Transaction:
        tax = 0
        if from_user not in (TREASURY, SINK) and to_user not in (TREASURY, SINK):
            rate = await self.repo.get_tax_rate(guild_id)
            if rate > 0:
                tax = amount * rate // 10000
        return await self.repo.transfer(guild_id, from_user, to_user, amount, reason, tax_amount=tax)

    async def grant(self, guild_id: str, user_id: str, amount: int, reason: str = "") -> Transaction:
        """Mint spi from the treasury faucet into an account."""
        return await self.repo.transfer(guild_id, TREASURY, user_id, amount, reason)

    async def burn(self, guild_id: str, user_id: str, amount: int, reason: str = "") -> Transaction:
        """Remove spi from circulation into the sink."""
        return await self.repo.transfer(guild_id, user_id, SINK, amount, reason)

    async def ledger(self, guild_id: str, user_id: str, limit: int = 20) -> list[Transaction]:
        return await self.repo.ledger(guild_id, user_id, limit)