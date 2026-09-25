import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent

# Discord Bot Token
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "").strip()

# Optional Guild ID for rapid command sync in development
GUILD_ID = os.getenv("GUILD_ID", "").strip()
GUILD_ID = int(GUILD_ID) if GUILD_ID.isdigit() else None

# Designated Channels
TASKS_CHANNEL_NAME = os.getenv("TASKS_CHANNEL_NAME", "tasks").lower().strip()
DEADLINES_CHANNEL_NAME = os.getenv("DEADLINES_CHANNEL_NAME", "deadlines").lower().strip()
SUBMISSIONS_CHANNEL_NAME = os.getenv("SUBMISSIONS_CHANNEL_NAME", "submissions").lower().strip()

# Database Path
DATABASE_PATH = os.getenv("DATABASE_PATH", "bot_database.sqlite")
if not os.path.isabs(DATABASE_PATH):
    DATABASE_PATH = str(BASE_DIR / DATABASE_PATH)

# File Submissions Directory
UPLOADS_DIR = str(BASE_DIR / "uploads")
os.makedirs(UPLOADS_DIR, exist_ok=True)

# Timezone
DEFAULT_TIMEZONE = os.getenv("DEFAULT_TIMEZONE", "UTC")
