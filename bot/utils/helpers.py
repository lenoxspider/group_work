import hashlib
import uuid
import re
from datetime import datetime, timezone
from typing import Optional, Tuple
import discord

def generate_short_id(prefix: str = "T") -> str:
    """Generates a clean short identifier, e.g., T-7A9B."""
    return f"{prefix}-{uuid.uuid4().hex[:6].upper()}"

def parse_datetime_input(date_str: str) -> Optional[datetime]:
    """
    Parses date strings such as:
    - YYYY-MM-DD
    - YYYY-MM-DD HH:MM
    - YYYY-MM-DDTHH:MM:SS
    Returns a timezone-aware UTC datetime or None if invalid.
    """
    cleaned = date_str.strip()
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%d",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%Y/%m/%d",
    ]
    for fmt in formats:
        try:
            dt = datetime.strptime(cleaned, fmt)
            # If no time was specified, default to 23:59:59 UTC
            if fmt in ("%Y-%m-%d", "%Y/%m/%d"):
                dt = dt.replace(hour=23, minute=59, second=59)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None

def to_discord_timestamps(dt: datetime) -> Tuple[str, str]:
    """Returns (absolute_timestamp, relative_countdown) for Discord markdown."""
    epoch = int(dt.timestamp())
    return f"<t:{epoch}:F>", f"<t:{epoch}:R>"

def calculate_time_remaining(due_dt: datetime) -> Tuple[int, int, int, bool]:
    """
    Returns (days, hours, minutes, is_past_due).
    """
    now = datetime.now(timezone.utc)
    diff = due_dt - now
    if diff.total_seconds() <= 0:
        return 0, 0, 0, True
    
    total_seconds = int(diff.total_seconds())
    days = total_seconds // 86400
    hours = (total_seconds % 86400) // 3600
    minutes = (total_seconds % 3600) // 60
    return days, hours, minutes, False

def format_countdown_string(due_dt: datetime) -> str:
    days, hours, minutes, is_past_due = calculate_time_remaining(due_dt)
    if is_past_due:
        return "⚠️ **OVERDUE**"
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0 or days > 0:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return "⏳ " + " ".join(parts) + " remaining"

def compute_file_hash(data: bytes) -> str:
    """Computes SHA-256 hash of bytes."""
    return hashlib.sha256(data).hexdigest()

def sanitize_filename(filename: str) -> str:
    """Replaces unsafe characters in a filename."""
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', filename)

async def get_or_create_channel(guild: discord.Guild, channel_name: str, topic: str = "") -> Optional[discord.TextChannel]:
    """Finds a channel with the given name or creates it if not found."""
    # Look for existing text channel
    for channel in guild.text_channels:
        if channel.name.lower() == channel_name.lower():
            return channel
    
    # Try creating channel if bot has permissions
    try:
        if guild.me.guild_permissions.manage_channels:
            return await guild.create_text_channel(name=channel_name, topic=topic)
    except Exception:
        pass
    return None
