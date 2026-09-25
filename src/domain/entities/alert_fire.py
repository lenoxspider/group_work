"""
Alert fire domain entity.

What it does:
- Models an idempotent notification fire record for a task and specific alert tier
  (e.g. 'T-24h', 'T-12h', 'T-2h', 'T-1h', 'T-0', 'DELINQUENT').

What it does NOT do:
- Does NOT execute discord notifications or database queries directly.
"""

from dataclasses import dataclass
from datetime import datetime

@dataclass(frozen=True)
class AlertFire:
    """Represents a recorded alert trigger preventing duplicate fires across restarts."""
    task_id: int
    alert_tier: str
    fired_at: datetime
