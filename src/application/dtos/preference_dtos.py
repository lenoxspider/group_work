"""
Member preference data transfer objects.

What it does:
- Encapsulates input and output payloads for student timezone and quiet hours workflows.

What it does NOT do:
- Does NOT contain business rules or validation logic.
"""

from dataclasses import dataclass

@dataclass(frozen=True)
class SetTimezoneDTO:
    """Input payload to configure a member's local timezone."""
    guild_id: str
    user_id: str
    timezone_name: str

@dataclass(frozen=True)
class SetQuietHoursDTO:
    """Input payload to configure a member's notification quiet hours."""
    guild_id: str
    user_id: str
    start_hour: int
    end_hour: int

@dataclass(frozen=True)
class MemberPreferenceDTO:
    """Output payload representing a member's notification preferences."""
    guild_id: str
    user_id: str
    timezone_name: str
    quiet_hours_start: int
    quiet_hours_end: int
    is_currently_quiet: bool
