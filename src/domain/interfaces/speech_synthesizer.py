"""
Speech synthesizer interface.

What it does:
- Defines the abstract contract for converting text to audio bytes.

What it does NOT do:
- Does NOT execute binaries or subprocesses directly.
"""

from typing import Protocol
from src.domain.entities.voice_profile import VoiceProfile

class SpeechSynthesizer(Protocol):
    """Abstract interface for speech synthesis implementations."""

    async def synthesize(self, text: str, profile: VoiceProfile) -> bytes:
        """
        Synthesizes text into raw WAV audio bytes using the given voice profile.

        Args:
            text: Text content to speak aloud.
            profile: VoiceProfile configuration (speed, pitch, voice_name).

        Returns:
            bytes: Valid WAV audio file bytes.
        """
        ...
