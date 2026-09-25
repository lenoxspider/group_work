"""
Discord Bot client composition root.

What it does:
- Bootstraps and injects domain repositories, application services, and Cogs.
- Synchronizes slash application commands with Discord Gateway.

What it does NOT do:
- Does NOT execute business logic or database queries directly.
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

from src.config.settings import Settings
from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.database.task_sqlite_repo import SQLiteTaskRepository
from src.infrastructure.database.deadline_sqlite_repo import SQLiteDeadlineRepository
from src.infrastructure.database.activity_sqlite_repo import SQLiteActivityRepository
from src.infrastructure.database.project_sqlite_repo import SQLiteProjectRepository
from src.infrastructure.database.extension_sqlite_repo import SQLiteExtensionRepository
from src.infrastructure.database.preference_sqlite_repo import SQLitePreferenceRepository
from src.infrastructure.database.squid_sqlite_repo import SquidSqliteRepository
from src.infrastructure.storage.local_file_vault import LocalFileVault
from src.infrastructure.speech.espeak_synthesizer import EspeakSpeechSynthesizer
from src.infrastructure.speech.attachment_deliverer import AttachmentAudioDeliverer

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
from src.interface.cogs.squid_cog import SquidCog, MoveCommandCog

logger = logging.getLogger("interface.bot")

class GroupAccountabilityBot(commands.Bot):
    """Composition root bot for Group Accountability."""

    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )
        self.settings = settings

        # Infrastructure Adapters
        self.db_manager = DatabaseManager(settings.database_path)
        self.task_repo = SQLiteTaskRepository(settings.database_path)
        self.deadline_repo = SQLiteDeadlineRepository(settings.database_path)
        self.activity_repo = SQLiteActivityRepository(settings.database_path)
        self.project_repo = SQLiteProjectRepository(settings.database_path)
        self.extension_repo = SQLiteExtensionRepository(settings.database_path)
        self.preference_repo = SQLitePreferenceRepository(settings.database_path)
        self.squid_repo = SquidSqliteRepository(settings.database_path)
        self.file_vault = LocalFileVault(settings.uploads_dir)

        # Application Services
        self.task_service = TaskService(self.task_repo, self.activity_repo)
        self.deadline_service = DeadlineService(self.deadline_repo)
        self.activity_service = ActivityService(self.activity_repo, self.task_repo)
        self.vault_service = VaultService(self.file_vault, self.activity_repo)
        self.extension_service = ExtensionService(self.extension_repo, self.task_repo)
        self.preference_service = PreferenceService(self.preference_repo)
        self.speech_synthesizer = EspeakSpeechSynthesizer(settings.tts_binary) if settings.tts_enabled else None
        self.audio_deliverer = AttachmentAudioDeliverer() if settings.tts_enabled else None
        self.voice_service = (
            VoiceService(self.speech_synthesizer, settings.tts_voice_default)
            if self.speech_synthesizer
            else None
        )
        self.squid_service = SquidService(self.squid_repo, self.speech_synthesizer)
        self.project_service = ProjectService(
            self.project_repo,
            self.task_repo,
            self.deadline_repo,
            self.activity_repo
        )

    async def setup_hook(self) -> None:
        """Initializes database schema and mounts all dependency-injected cogs."""
        logger.info("Initializing database schema...")
        await self.db_manager.initialize_schema()

        # Mount Cogs with injected services
        await self.add_cog(TasksCog(
            self, self.task_service, self.extension_service, self.preference_service, self.voice_service
        ))
        await self.add_cog(TaskReminderCog(
            self, self.task_service, self.preference_service, self.voice_service, self.squid_service
        ))
        await self.add_cog(DeadlinesCog(self, self.deadline_service, self.voice_service))
        await self.add_cog(ReportsCog(self, self.activity_service, self.voice_service))
        await self.add_cog(TrackerCog(self, self.activity_service, self.vault_service))
        await self.add_cog(AdminCog(self, self.project_service))
        await self.add_cog(PreferenceCog(self, self.preference_service))
        if self.voice_service and self.audio_deliverer:
            await self.add_cog(VoiceCog(self, self.voice_service, self.audio_deliverer))
        if self.audio_deliverer:
            await self.add_cog(SquidCog(self, self.squid_service, self.audio_deliverer, self.speech_synthesizer))
            await self.add_cog(MoveCommandCog(self, self.squid_service, self.audio_deliverer))
        logger.info("All Cogs mounted successfully.")

        # Register Global Tree Error Handler
        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            orig_error = getattr(error, "original", error)
            if isinstance(orig_error, discord.NotFound):
                logger.warning("Discord interaction %s expired before response could be sent.", interaction.id)
                return
            logger.error("Unhandled slash command error: %s", error, exc_info=orig_error)

        # Sync Slash Commands
        try:
            if self.settings.guild_id:
                guild_obj = discord.Object(id=self.settings.guild_id)
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                logger.info("Instantly synced %d commands to Guild ID %s", len(synced), self.settings.guild_id)
            else:
                synced = await self.tree.sync()
                logger.info("Synced %d global slash commands.", len(synced))
        except Exception as e:
            logger.error("Failed to sync slash commands: %s", e, exc_info=True)

    async def on_ready(self) -> None:
        logger.info("Connected to Discord as %s#%s (ID: %s)", self.user.name, self.user.discriminator, self.user.id)
        activity = discord.Activity(type=discord.ActivityType.watching, name="group milestones & tasks")
        await self.change_presence(status=discord.Status.online, activity=activity)
