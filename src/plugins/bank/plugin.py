"""Bank feature plugin - registers schema and cogs against the bot runtime."""

from src.plugins.base import Plugin
from src.plugins.bank.cog import BankCog
from src.plugins.bank.repository import SQLiteBankRepository
from src.plugins.bank.schema import BANK_SCHEMA
from src.plugins.bank.service import BankService


class BankPlugin(Plugin):
    name = "bank"
    title = "🏦 Bank & spi Economy"
    summary = "The ledger. spi is minted, transferred, taxed, and burned here."
    guide = [
        ("/bank balance", "Check a member's spi balance"),
        ("/bank give <@member> <amount>", "Send spi (minus transfer tax)"),
        ("/bank ledger", "Your recent transactions"),
        ("/bank grant · burn", "[Admin] Mint from the treasury, or burn from circulation"),
    ]
    schema = BANK_SCHEMA

    def __init__(self, bot):
        self.bot = bot
        self.repo = SQLiteBankRepository(bot.settings.database_path)
        self.service = BankService(self.repo)

    def build_cogs(self, bot) -> list:
        return [BankCog(bot, self.service)]