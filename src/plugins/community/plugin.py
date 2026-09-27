"""Community feature plugin - onboarding and the constitution gate."""

from src.interface.channel_manager import ChannelDecl
from src.plugins.base import Plugin
from src.plugins.community.cog import CommunityCog
from src.plugins.community.repository import SQLiteCommunityRepository
from src.plugins.community.schema import COMMUNITY_SCHEMA
from src.plugins.community.service import CommunityService


class CommunityPlugin(Plugin):
    name = "community"
    title = "🐱 Community & Membership"
    summary = "Join, sign the constitution, and earn citizenship (and your vote)."
    guide = [
        ("/join", "Sign the constitution and become a citizen (unlocks voting)"),
        ("/me", "Your membership status, intro task, and wallet"),
    ]
    schema = COMMUNITY_SCHEMA
    migrations = []

    def __init__(self, bot):
        self.bot = bot
        self.repo = SQLiteCommunityRepository(bot.settings.database_path)
        self.service = CommunityService(self.repo)

        self.channels = [
            ChannelDecl(
                "new-recruits",
                "👋 New members introduce themselves here. Task #1 for every catizen.",
                "recruits",
            ),
        ]

    def wire(self, registry) -> None:
        bank = registry.get("bank")
        if bank:
            self.service.attach_bank(bank.service)
        groupwork = registry.get("groupwork")
        if groupwork:
            self.service.attach_task_service(groupwork.task_service)
        society = registry.get("society")
        if society:
            self.service.attach_society(society.service)

    def build_cogs(self, bot) -> list:
        return [CommunityCog(bot, self.service, channel_router=bot.channel_router)]