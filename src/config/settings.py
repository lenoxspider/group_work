"""
Configuration settings loader and validator.

What it does:
- Loads environment variables from .env or system environment.
- Validates required configurations and normalizes path formats.
- Provides a strongly typed, immutable Settings object.

What it does NOT do:
- Does NOT execute business logic or open database connections.
- Does NOT interact with Discord APIs.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

# Load .env once at module import
load_dotenv()

@dataclass(frozen=True)
class Settings:
    """Immutable application settings container."""
    bot_token: str
    guild_id: Optional[int]
    tasks_channel: str
    deadlines_channel: str
    submissions_channel: str
    wall_of_shame_channel: str
    database_path: str
    uploads_dir: str
    default_timezone: str
    tts_enabled: bool
    tts_engine: str
    tts_binary: str
    tts_voice_default: str
    tts_delivery: str

    @classmethod
    def load(cls) -> "Settings":
        """
        Loads configuration from environment variables.

        Returns:
            Settings: Validated typed configuration instance.
        """
        root_dir = Path(__file__).resolve().parent.parent.parent
        raw_token = os.getenv("DISCORD_BOT_TOKEN", "").strip()
        raw_guild = os.getenv("GUILD_ID", "").strip()
        guild_id = int(raw_guild) if raw_guild.isdigit() else None

        db_path = os.getenv("DATABASE_PATH", "bot_database.sqlite").strip()
        if not os.path.isabs(db_path):
            db_path = str(root_dir / db_path)

        uploads_dir = str(root_dir / "uploads")
        os.makedirs(uploads_dir, exist_ok=True)

        win_espeak = r"C:\Program Files\eSpeak NG\espeak-ng.exe"
        default_espeak = win_espeak if os.path.exists(win_espeak) else "espeak-ng"
        tts_binary = os.getenv("TTS_BINARY", default_espeak).strip()
        tts_enabled_raw = os.getenv("TTS_ENABLED", "true").strip().lower()
        tts_enabled = tts_enabled_raw in ("true", "1", "yes")

        return cls(
            bot_token=raw_token,
            guild_id=guild_id,
            tasks_channel=os.getenv("TASKS_CHANNEL_NAME", "tasks").lower().strip(),
            deadlines_channel=os.getenv("DEADLINES_CHANNEL_NAME", "deadlines").lower().strip(),
            submissions_channel=os.getenv("SUBMISSIONS_CHANNEL_NAME", "submissions").lower().strip(),
            wall_of_shame_channel=os.getenv("WALL_OF_SHAME_CHANNEL_NAME", "wall-of-shame").lower().strip(),
            database_path=db_path,
            uploads_dir=uploads_dir,
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "UTC").strip(),
            tts_enabled=tts_enabled,
            tts_engine=os.getenv("TTS_ENGINE", "espeak-ng").strip().lower(),
            tts_binary=tts_binary,
            tts_voice_default=os.getenv("TTS_VOICE_DEFAULT", "en-us").strip().lower(),
            tts_delivery=os.getenv("TTS_DELIVERY", "attachment").strip().lower()
        )
