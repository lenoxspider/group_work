"""
Voice data transfer objects.

What it does:
- Encapsulates input requests and output payloads for voice synthesis workflows.

What it does NOT do:
- Does NOT contain business rules or execute subprocesses.
"""

from dataclasses import dataclass
from typing import Optional

@dataclass(frozen=True)
class SynthesizeRequestDTO:
    """Input payload to request speech synthesis."""
    text: str
    user_id: Optional[str] = None
    tone: Optional[str] = "serious"
    language: Optional[str] = "en-us"

@dataclass(frozen=True)
class AudioClipDTO:
    """Output payload representing a synthesized audio clip."""
    audio_bytes: bytes
    filename: str
    transcript: str
    tone: str
    language: str
