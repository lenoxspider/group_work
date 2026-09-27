"""Radio feature plugin - YouTube audio streaming into voice channels."""

from src.plugins.base import Plugin
from src.plugins.radio.cog import RadioCog
from src.plugins.radio.resolver import SourceResolver
from src.plugins.radio.service import RadioService
from src.interface.channel_manager import ChannelDecl


class RadioPlugin(Plugin):
    name = "radio"
    schema = []
    migrations = []

    def __init__(self, bot):
        self.bot = bot
        self.resolver = SourceResolver()
        self.service = RadioService(bot, self.resolver, bot.channel_router)

        self.channels = [
            ChannelDecl(
                "radio",
                "📻 Radio station. Now-playing announcements appear here.",
                "ledger",
            ),
        ]

    def build_cogs(self, bot) -> list:
        return [RadioCog(bot, self.service)]