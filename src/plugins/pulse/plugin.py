"""Pulse feature plugin - bot-initiated engagement moments."""

from src.interface.channel_manager import ChannelDecl
from src.plugins.base import Plugin
from src.plugins.pulse.cog import PulseCog
from src.plugins.pulse.repository import SQLitePulseRepository
from src.plugins.pulse.schema import PULSE_SCHEMA
from src.plugins.pulse.service import PulseService


class PulsePlugin(Plugin):
    name = "pulse"
    title = "⚡ The Pulse"
    summary = "The bot pulls the trigger - short reflex moments that keep the hall alive."
    guide = [
        ("/pulse status", "Is a pulse live right now?"),
        ("/pulse fire", "[Admin] Fire a pulse immediately"),
    ]
    schema = PULSE_SCHEMA
    migrations = []

    def __init__(self, bot):
        self.bot = bot
        self.repo = SQLitePulseRepository(bot.settings.database_path)
        self.service = PulseService(self.repo)

        self.channels = [
            ChannelDecl(
                "pulse",
                "⚡ The pulse. Bot-fired moments land here - keep an eye on it.",
                "pulse",
            ),
        ]

    def wire(self, registry) -> None:
        bank = registry.get("bank")
        if bank:
            self.service.attach_bank(bank.service)

    def build_cogs(self, bot) -> list:
        return [PulseCog(bot, self.service, channel_router=bot.channel_router)]