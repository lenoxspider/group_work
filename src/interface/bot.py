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
from discord.ext import commands

from src.config.settings import Settings
from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.database.task_sqlite_repo import SQLiteTaskRepository
from src.infrastructure.database.deadline_sqlite_repo import SQLiteDeadlineRepository
from src.infrastructure.database.activity_sqlite_repo import SQLiteActivityRepository
from src.infrastructure.database.project_sqlite_repo import SQLiteProjectRepository
from src.infrastructure.database.extension_sqlite_repo import SQLiteExtensionRepository
from src.infrastructure.database.preference_sqlite_repo import SQLitePreferenceRepository
from src.infrastructure.storage.local_file_vault import LocalFileVault

from src.application.services.task_service import TaskService
from src.application.services.deadline_service import DeadlineService
from src.application.services.activity_service import ActivityService
from src.application.services.vault_service import VaultService
from src.application.services.project_service import ProjectService
from src.application.services.extension_service import ExtensionService
from src.application.services.preference_service import PreferenceService

from src.interface.cogs.tasks_cog import TasksCog
from src.interface.cogs.deadlines_cog import DeadlinesCog
from src.interface.cogs.reports_cog import ReportsCog
from src.interface.cogs.tracker_cog import TrackerCog
from src.interface.cogs.admin_cog import AdminCog
from src.interface.cogs.preference_cog import PreferenceCog

logger = logging.getLogger("interface.bot")

class GroupAccountabilityBot(commands.Bot):
    """Composition root bot for Group Accountability."""

    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.members = True
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
        self.file_vault = LocalFileVault(settings.uploads_dir)

        # Application Services
        self.task_service = TaskService(self.task_repo, self.activity_repo)
        self.deadline_service = DeadlineService(self.deadline_repo)
        self.activity_service = ActivityService(self.activity_repo, self.task_repo)
        self.vault_service = VaultService(self.file_vault, self.activity_repo)
        self.extension_service = ExtensionService(self.extension_repo, self.task_repo)
        self.preference_service = PreferenceService(self.preference_repo)
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
        await self.add_cog(TasksCog(self, self.task_service, self.extension_service, self.preference_service))
        await self.add_cog(DeadlinesCog(self, self.deadline_service))
        await self.add_cog(ReportsCog(self, self.activity_service))
        await self.add_cog(TrackerCog(self, self.activity_service, self.vault_service))
        await self.add_cog(AdminCog(self, self.project_service))
        await self.add_cog(PreferenceCog(self, self.preference_service))
        logger.info("All Cogs mounted successfully.")

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
