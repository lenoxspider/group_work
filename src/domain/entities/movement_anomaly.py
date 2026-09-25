"""
Movement anomaly domain entity.

What it does:
- Models suspicious, out-of-order, or late movement attempts during Red Light Green Light.
- Provides audit trails for anti-cheat and telemetry.

What it does NOT do:
- Does NOT perform database I/O or Discord messaging.
"""

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class MovementAnomaly:
    """Represents a flagged movement violation or close-call event."""
    guild_id: str
    user_id: str
    occurred_at: datetime
    reason: str
