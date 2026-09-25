"""
Application entrypoint script.

What it does:
- Bootstraps typed settings.
- Configures standard structured logging.
- Starts the GroupAccountabilityBot event loop.

What it does NOT do:
- Does NOT execute business logic or database queries directly.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.config.settings import Settings
from src.interface.bot import GroupAccountabilityBot

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("run")

async def main() -> None:
    settings = Settings.load()
    if not settings.bot_token:
        logger.error(
            "DISCORD_BOT_TOKEN is not configured.\n"
            "Please copy .env.example to .env and set your token from the Discord Developer Portal."
        )
        sys.exit(1)

    bot = GroupAccountabilityBot(settings)
    async with bot:
        await bot.start(settings.bot_token)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot execution terminated by user.")
