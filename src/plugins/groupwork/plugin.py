"""Groupwork feature plugin - accountability, squid game, and voice.

This owns everything the GroupAccountabilityBot used to hardcode inline:
repositories, file vault, channel router, application services, and cogs.
The bot's composition root now only constructs shared infrastructure
(db manager, TTS engine) and lets this plugin self-register.
"""

from src.plugins.base import Plugin
from src.plugins.groupwork.schema import GROUPWORK_MIGRATIONS, GROUPWORK_SCHEMA
from src.interface.channel_manager import ChannelDecl

from src.infrastructure.database.task_sqlite_repo import SQLiteTaskRepository
from src.infrastructure.database.deadline_sqlite_repo import SQLiteDeadlineRepository
from src.infrastructure.database.activity_sqlite_repo import SQLiteActivityRepository
from src.infrastructure.database.project_sqlite_repo import SQLiteProjectRepository
from src.infrastructure.database.extension_sqlite_repo import SQLiteExtensionRepository
from src.infrastructure.database.preference_sqlite_repo import SQLitePreferenceRepository
from src.infrastructure.database.squid_sqlite_repo import SquidSqliteRepository
from src.infrastructure.database.alert_fire_sqlite_repo import SQLiteAlertFireRepository
from src.infrastructure.storage.local_file_vault import LocalFileVault

from src.application.services.task_service import TaskService
from src.application.services.deadline_service import DeadlineService
from src.application.services.activity_service import ActivityService
from src.application.services.vault_service import VaultService
from src.application.services.project_service import ProjectService
from src.application.services.extension_service import ExtensionService
from src.application.services.preference_service import PreferenceService
from src.application.services.voice_service import VoiceService
from src.application.services.squid_service import SquidService

from src.interface.cogs.tasks_cog import TasksCog
from src.interface.cogs.task_reminder_cog import TaskReminderCog
from src.interface.cogs.deadlines_cog import DeadlinesCog
from src.interface.cogs.reports_cog import ReportsCog
from src.interface.cogs.tracker_cog import TrackerCog
from src.interface.cogs.admin_cog import AdminCog
from src.interface.cogs.preference_cog import PreferenceCog
from src.interface.cogs.voice_cog import VoiceCog
from src.interface.cogs.squid_cog import SquidCog
from src.interface.cogs.move_command_cog import MoveCommandCog
from src.interface.cogs.cleanup_cog import CleanupCog


class GroupworkPlugin(Plugin):
    name = "groupwork"
    schema = GROUPWORK_SCHEMA
    migrations = GROUPWORK_MIGRATIONS

    def __init__(self, bot):
        self.bot = bot
        settings = bot.settings

        # Declared channels: ledger names come from config, game channels are fixed
        self.channels = [
            ChannelDecl(settings.tasks_channel, "📋 Group task ledger. Read-only display. Use /task to interact.", "ledger"),
            ChannelDecl(settings.deadlines_channel, "🎯 Major project milestones and live countdowns. Read-only display.", "ledger"),
            ChannelDecl(settings.submissions_channel, "📥 Verified deliverable submission vault. Read-only audit receipts.", "ledger"),
            ChannelDecl(settings.wall_of_shame_channel, "🚨 Public accountability ledger. Overdue tasks recorded here.", "ledger"),
            ChannelDecl(
                "game-hub",
                "🎮 Squid Game Arena. Only active Players can execute commands.",
                "arena",
                welcome="○ △ □ SQUID GAME ARENA • INITIALIZED\n\n"
                        "**How to play:**\n"
                        "• Type `/squid join` to claim your player tag (`001`–`456`) and gain arena access.\n"
                        "• Eliminated players are moved to the private <#spectators> lounge.\n"
                        "• Obey all directives from the Masked Guards.",
            ),
            ChannelDecl("spectators", "💀 Observation deck for eliminated contestants.", "spectators"),
            ChannelDecl("bot-log", "🛡️ Bot admin and security audit log. Private to staff and bot.", "bot-log"),
        ]

        # Shared channel infrastructure lives on the bot core
        self.channel_router = bot.channel_router

        # Repositories & storage
        self.task_repo = SQLiteTaskRepository(settings.database_path)
        self.deadline_repo = SQLiteDeadlineRepository(settings.database_path)
        self.activity_repo = SQLiteActivityRepository(settings.database_path)
        self.project_repo = SQLiteProjectRepository(settings.database_path)
        self.extension_repo = SQLiteExtensionRepository(settings.database_path)
        self.preference_repo = SQLitePreferenceRepository(settings.database_path)
        self.squid_repo = SquidSqliteRepository(settings.database_path)
        self.alert_fire_repo = SQLiteAlertFireRepository(settings.database_path)
        self.file_vault = LocalFileVault(settings.uploads_dir)

        # Services
        self.task_service = TaskService(self.task_repo, self.activity_repo)
        self.deadline_service = DeadlineService(self.deadline_repo)
        self.activity_service = ActivityService(self.activity_repo, self.task_repo)
        self.vault_service = VaultService(self.file_vault, self.activity_repo)
        self.extension_service = ExtensionService(self.extension_repo, self.task_repo)
        self.preference_service = PreferenceService(self.preference_repo)
        self.voice_service = (
            VoiceService(bot.speech_synthesizer, settings.tts_voice_default)
            if bot.speech_synthesizer
            else None
        )
        self.squid_service = SquidService(self.squid_repo, bot.speech_synthesizer)
        self.project_service = ProjectService(
            self.project_repo,
            self.task_repo,
            self.deadline_repo,
            self.activity_repo,
        )

    def build_cogs(self, bot) -> list:
        cogs = [
            TasksCog(bot, self.task_service, self.extension_service, self.channel_router, self.preference_service, self.voice_service),
            TaskReminderCog(bot, self.task_service, self.channel_router, self.alert_fire_repo, self.preference_service, self.voice_service, self.squid_service),
            DeadlinesCog(bot, self.deadline_service, self.channel_router, self.voice_service),
            ReportsCog(bot, self.activity_service, self.voice_service),
            TrackerCog(bot, self.activity_service, self.vault_service, self.channel_router),
            AdminCog(bot, self.project_service),
            PreferenceCog(bot, self.preference_service),
            CleanupCog(bot, self.channel_router),
        ]
        if self.voice_service and bot.audio_deliverer:
            cogs.append(VoiceCog(bot, self.voice_service, bot.audio_deliverer))
        if bot.audio_deliverer:
            cogs.append(SquidCog(bot, self.squid_service, bot.audio_deliverer, bot.speech_synthesizer, self.channel_router))
            cogs.append(MoveCommandCog(bot, self.squid_service, bot.audio_deliverer, self.channel_router))
        return cogs

    async def on_setup(self, bot) -> None:
        # Re-sync and cleanup game session state on startup
        self.squid_service.reset_all_games()
        if bot.speech_synthesizer:
            try:
                await self.squid_service.preload_audio_cache()
            except Exception as e:
                import logging
                logging.getLogger("groupwork").warning("Could not pre-synthesize Squid Game audio cache: %s", e)