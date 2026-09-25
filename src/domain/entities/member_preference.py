"""
Member preference aggregate entity.

What it does:
- Models individual student timezone and quiet hours (DND) settings.
- Computes whether an incoming notification falls into quiet hours.

What it does NOT do:
- Does NOT execute SQL or database connections.
- Does NOT send Discord messages.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from src.domain.errors import ValidationError

@dataclass
class MemberPreference:
    """Represents a member's timezone and quiet hours notification settings."""
    guild_id: str
    user_id: str
    timezone_name: str = "UTC"
    quiet_hours_start: int = 23  # 11 PM
    quiet_hours_end: int = 8     # 8 AM
    updated_at: datetime = datetime.now(timezone.utc)

    def __post_init__(self):
        if not self.guild_id.strip():
            raise ValidationError("Guild ID cannot be empty.")
        if not self.user_id.strip():
            raise ValidationError("User ID cannot be empty.")
        if not (0 <= self.quiet_hours_start <= 23) or not (0 <= self.quiet_hours_end <= 23):
            raise ValidationError("Quiet hours must be integers between 0 and 23.")
        try:
            ZoneInfo(self.timezone_name)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise ValidationError(f"Invalid IANA timezone '{self.timezone_name}': {e}")

    def is_in_quiet_hours(self, utc_time: datetime) -> bool:
        """
        Determines whether the given UTC timestamp falls during member's local quiet hours.

        Args:
            utc_time: Timestamp in UTC.

        Returns:
            bool: True if member is currently in quiet hours, False otherwise.
        """
        tz = ZoneInfo(self.timezone_name)
        local_time = utc_time.astimezone(tz)
        hour = local_time.hour

        if self.quiet_hours_start == self.quiet_hours_end:
            return False

        if self.quiet_hours_start > self.quiet_hours_end:
            # Crosses midnight (e.g. 23:00 to 08:00)
            return hour >= self.quiet_hours_start or hour < self.quiet_hours_end
        else:
            # Same day window (e.g. 01:00 to 07:00)
            return self.quiet_hours_start <= hour < self.quiet_hours_end
