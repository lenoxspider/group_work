"""Offices feature plugin - the positions of state."""

from src.plugins.base import Plugin
from src.plugins.offices.cog import OfficesCog
from src.plugins.offices.repository import SQLiteOfficesRepository
from src.plugins.offices.schema import OFFICES_SCHEMA
from src.plugins.offices.service import OfficesService


class OfficesPlugin(Plugin):
    name = "offices"
    title = "🎖️ Offices of State"
    summary = "Magistrate, Treasurer, Front Man - the offices citizens hold."
    guide = [
        ("/office appoint <office> <member>", "[Admin] Appoint a citizen to an office"),
        ("/office vacate <office>", "[Admin] Vacate an office"),
        ("/office list", "Who holds which office, and what each does"),
    ]
    schema = OFFICES_SCHEMA
    migrations = []

    def __init__(self, bot):
        self.bot = bot
        self.repo = SQLiteOfficesRepository(bot.settings.database_path)
        self.service = OfficesService(self.repo)

    def wire(self, registry) -> None:
        chronicle = registry.get("chronicle")
        if chronicle:
            self.service.attach_chronicle(chronicle.service)

    def build_cogs(self, bot) -> list:
        return [OfficesCog(bot, self.service)]
