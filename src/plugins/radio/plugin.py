"""Radio feature plugin - YouTube audio streaming into voice channels."""

from src.plugins.base import Plugin
from src.plugins.radio.cog import RadioCog
from src.plugins.radio.resolver import SourceResolver
from src.plugins.radio.service import RadioService
from src.interface.channel_manager import ChannelDecl


class RadioPlugin(Plugin):
    name = "radio"
    title = "📻 Radio Station"
    summary = "YouTube audio streamed straight into a voice channel."
    guide = [
        ("/radio play <url|search>", "Queue a track in your voice channel"),
        ("/radio skip · stop", "Skip the current track, or disconnect"),
        ("/radio queue · now", "See what's queued and what's playing"),
    ]
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