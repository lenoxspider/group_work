"""Groupwork feature plugin - accountability and voice.

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

from src.interface.cogs.tasks_cog import TasksCog
from src.interface.cogs.task_reminder_cog import TaskReminderCog
from src.interface.cogs.deadlines_cog import DeadlinesCog
from src.interface.cogs.reports_cog import ReportsCog
from src.interface.cogs.tracker_cog import TrackerCog
from src.interface.cogs.admin_cog import AdminCog
from src.interface.cogs.preference_cog import PreferenceCog
from src.interface.cogs.voice_cog import VoiceCog
from src.interface.cogs.cleanup_cog import CleanupCog


BOUNTY_ASSIGNMENT = 50
BOUNTY_VERIFICATION = 10
FINE_OVERDUE = 25


class GroupworkPlugin(Plugin):
    name = "groupwork"
    title = "📋 Work & Accountability"
    summary = "Tasks pay spi, overdue tasks are fined. Work to earn, deliver on time."
    guide = [
        ("/task add <desc> <@member> <due>", "Assign a task (optional verifier buddy)"),
        ("/task complete · verify · extend · list", "Deliverables, voting, and extensions"),
        ("/deadline add · list · complete", "Milestone countdowns with team alerts"),
        ("/report [@member]", "Leaderboard, military ranks, and scorecards"),
        ("/submit <file>", "Deliverable vault with SHA-256 verification"),
        ("/timezone set · quiet · view", "IANA timezone and quiet hours"),
        ("/project status · finish", "Sprint health dashboard and archive"),
        ("/setup", "Provision channels, roles, and permissions"),
    ]
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
        self.alert_fire_repo = SQLiteAlertFireRepository(settings.database_path)
        self.file_vault = LocalFileVault(settings.uploads_dir)

        # Services
        self.task_service = TaskService(
            self.task_repo,
            self.activity_repo,
            bounty_assignment=BOUNTY_ASSIGNMENT,
            bounty_verification=BOUNTY_VERIFICATION,
            fine_overdue=FINE_OVERDUE,
        )
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
        self.project_service = ProjectService(
            self.project_repo,
            self.task_repo,
            self.deadline_repo,
            self.activity_repo,
        )

    def wire(self, registry) -> None:
        """Inject the bank's ledger into the task service for work-to-earn rewards."""
        bank_plugin = registry.get("bank")
        if bank_plugin:
            self.task_service.attach_ledger(bank_plugin.service)

    def build_cogs(self, bot) -> list:
        cogs = [
            TasksCog(bot, self.task_service, self.extension_service, self.channel_router, self.preference_service, self.voice_service),
            TaskReminderCog(bot, self.task_service, self.channel_router, self.alert_fire_repo, self.preference_service, self.voice_service),
            DeadlinesCog(bot, self.deadline_service, self.channel_router, self.voice_service),
            ReportsCog(bot, self.activity_service, self.voice_service),
            TrackerCog(bot, self.activity_service, self.vault_service, self.channel_router),
            AdminCog(bot, self.project_service),
            PreferenceCog(bot, self.preference_service),
            CleanupCog(bot, self.channel_router),
        ]
        if self.voice_service and bot.audio_deliverer:
            cogs.append(VoiceCog(bot, self.voice_service, bot.audio_deliverer))
        return cogs

    async def on_setup(self, bot) -> None:
        pass