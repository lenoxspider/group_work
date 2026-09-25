"""
Channel binding domain entity.

What it does:
- Models the persistent mapping between a logical channel key (e.g. 'tasks', 'game-hub')
  and its concrete Discord snowflake ID in a specific guild.

What it does NOT do:
- Does NOT perform database I/O or Discord API calls.
"""

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class ChannelBinding:
    """Represents a bound Discord channel ID for a logical role in a guild."""
    guild_id: str
    channel_key: str
    channel_id: str
    updated_at: datetime
