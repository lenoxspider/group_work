"""Chronicle feature plugin - the state's memory."""

from src.interface.channel_manager import ChannelDecl
from src.plugins.base import Plugin
from src.plugins.chronicle.cog import ChronicleCog
from src.plugins.chronicle.repository import SQLiteChronicleRepository
from src.plugins.chronicle.schema import CHRONICLE_SCHEMA
from src.plugins.chronicle.service import ChronicleService


class ChroniclePlugin(Plugin):
    name = "chronicle"
    title = "📜 The Chronicle"
    summary = "The state records its own history - signings, verdicts, Games, laws, Snap Trials."
    guide = [
        ("/chronicle recent [limit]", "Read the recent history of the collective"),
        ("/chronicle state", "A digest of everything the chronicle holds"),
    ]
    schema = CHRONICLE_SCHEMA
    migrations = []

    def __init__(self, bot):
        self.bot = bot
        self.repo = SQLiteChronicleRepository(bot.settings.database_path)
        self.service = ChronicleService(self.repo)
        self.channels = [
            ChannelDecl(
                "chronicle",
                "📜 The recorded history of the collective. Only the state writes here.",
                "ledger",
            ),
        ]

    def build_cogs(self, bot) -> list:
        return [ChronicleCog(bot, self.service, channel_router=bot.channel_router)]
