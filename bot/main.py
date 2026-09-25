import asyncio
import logging
import sys
import discord
from discord.ext import commands

from bot.config import DISCORD_BOT_TOKEN, GUILD_ID
from bot.database import db_instance

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("bot.main")

class GroupAccountabilityBot(commands.Bot):
    def __init__(self):
        # Configure required Discord Intents
        intents = discord.Intents.default()
        intents.message_content = True  # Required for message activity counting
        intents.guilds = True           # Required for channel management
        intents.members = True          # Required for tracking member contributions
        intents.messages = True         # Required for on_message tracking & DMs

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None
        )

    async def setup_hook(self):
        # 1. Initialize SQLite Database Schema
        logger.info("Initializing SQLite database...")
        await db_instance.initialize()

        # 2. Load Cogs
        cogs = [
            "bot.cogs.admin",
            "bot.cogs.tasks",
            "bot.cogs.deadlines",
            "bot.cogs.tracker",
            "bot.cogs.reports"
        ]
        for cog in cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Loaded extension: {cog}")
            except Exception as e:
                logger.error(f"Failed to load extension {cog}: {e}", exc_info=True)

        # 3. Synchronize Slash Commands
        try:
            if GUILD_ID:
                guild_obj = discord.Object(id=GUILD_ID)
                self.tree.copy_global_to(guild=guild_obj)
                synced = await self.tree.sync(guild=guild_obj)
                logger.info(f"Instantly synced {len(synced)} slash commands to Guild ID: {GUILD_ID}")
            else:
                synced = await self.tree.sync()
                logger.info(f"Synced {len(synced)} global slash commands (may take up to an hour to propagate without GUILD_ID).")
        except Exception as e:
            logger.error(f"Error syncing slash commands: {e}", exc_info=True)

    async def on_ready(self):
        logger.info("--------------------------------------------------")
        logger.info(f"Bot connected successfully as: {self.user.name}#{self.user.discriminator} (ID: {self.user.id})")
        logger.info(f"Serving {len(self.guilds)} server(s).")
        logger.info("--------------------------------------------------")
        activity = discord.Activity(type=discord.ActivityType.watching, name="group milestones & tasks")
        await self.change_presence(status=discord.Status.online, activity=activity)

async def main():
    if not DISCORD_BOT_TOKEN:
        logger.error(
            "DISCORD_BOT_TOKEN is not set in environment or .env file!\n"
            "Please copy .env.example to .env and insert your bot token from the Discord Developer Portal."
        )
        return

    bot = GroupAccountabilityBot()
    async with bot:
        await bot.start(DISCORD_BOT_TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
