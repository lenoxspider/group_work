"""
Discord Bot client composition root.

What it does:
- Owns shared infrastructure only: database manager, TTS engine, audio deliverer.
- Loads feature plugins (bank, groupwork, ...), each of which self-registers
  its schema, services, and cogs.

What it does NOT do:
- Does NOT hardcode any feature's repositories, services, or cogs.
- Does NOT execute business logic or database queries directly.
"""

import logging
import discord
from discord import app_commands
from discord.ext import commands

from src.config.settings import Settings
from src.infrastructure.database.connection import DatabaseManager
from src.infrastructure.speech.espeak_synthesizer import EspeakSpeechSynthesizer
from src.infrastructure.speech.attachment_deliverer import AttachmentAudioDeliverer

from src.plugins import get_plugins

logger = logging.getLogger("interface.bot")


class GroupAccountabilityBot(commands.Bot):
    """Composition root: shared core + plugin runtime."""

    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.guilds = True
        intents.messages = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,
        )
        self.settings = settings

        # Shared core infrastructure
        self.db_manager = DatabaseManager(settings.database_path)
        self.speech_synthesizer = (
            EspeakSpeechSynthesizer(settings.tts_binary) if settings.tts_enabled else None
        )
        self.audio_deliverer = AttachmentAudioDeliverer() if settings.tts_enabled else None

        # Plugin runtime: every feature self-registers schema, services, and cogs
        self.plugins = {}
        self._plugin_defs = get_plugins(self)
        for plugin in self._plugin_defs:
            self.plugins[plugin.name] = plugin
            self.db_manager.register_plugin_schema(plugin.name, plugin.schema)
            self.db_manager.register_plugin_migrations(plugin.name, plugin.migrations)

    async def setup_hook(self) -> None:
        logger.info("Initializing database schema...")
        await self.db_manager.initialize_schema()

        # Resolve cross-plugin references before mounting
        for plugin in self._plugin_defs:
            plugin.wire(self.plugins)

        # Mount every plugin's cogs
        for plugin in self._plugin_defs:
            for cog in plugin.build_cogs(self):
                await self.add_cog(cog)
            logger.info("Plugin mounted: %s", plugin.name)

        # Post-mount async hooks (caches, state resets)
        for plugin in self._plugin_defs:
            await plugin.on_setup(self)

        # Register Global Tree Error Handler
        @self.tree.error
        async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
            orig_error = getattr(error, "original", error)
            if isinstance(error, app_commands.CommandOnCooldown):
                msg = f"⏳ **Slow down!** Cooldown active ({error.retry_after:.1f}s remaining)."
                try:
                    if interaction.response.is_done():
                        await interaction.followup.send(msg, ephemeral=True)
                    else:
                        await interaction.response.send_message(msg, ephemeral=True)
                except Exception:
                    pass
                return
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