"""Society feature plugin - constitution, citizenship, treasury, and governance."""

from src.plugins.base import Plugin
from src.plugins.society.cog import SocietyCog
from src.plugins.society.repository import SocietyRepository
from src.plugins.society.schema import SOCIETY_SCHEMA
from src.plugins.society.service import SocietyService
from src.interface.channel_manager import ChannelDecl


class SocietyPlugin(Plugin):
    name = "society"
    schema = SOCIETY_SCHEMA
    migrations = []

    def __init__(self, bot):
        self.bot = bot
        self.repo = SocietyRepository(bot.settings.database_path)
        self.service = SocietyService(self.repo)

        self.channels = [
            ChannelDecl(
                "town-hall",
                "🏛️ Society town hall. Proposals and laws are announced here.",
                "ledger",
            ),
        ]

    def wire(self, registry) -> None:
        bank_plugin = registry.get("bank")
        if bank_plugin:
            self.service.attach_bank(bank_plugin.service)

    def build_cogs(self, bot) -> list:
        return [SocietyCog(bot, self.service)]