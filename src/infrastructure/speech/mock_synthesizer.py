"""
Mock speech synthesizer for tests and fallback.

What it does:
- Generates a valid RIFF/WAV audio stream using Python's standard library.
- Enables complete test isolation without requiring external binaries.

What it does NOT do:
- Does NOT execute external processes or audio hardware.
"""

import io
import wave
import struct
from src.domain.entities.voice_profile import VoiceProfile
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer

class MockSpeechSynthesizer(SpeechSynthesizer):
    """Generates valid synthesized PCM WAV audio in memory."""

    def __init__(self, sample_rate: int = 16000, duration_seconds: float = 0.5):
        self.sample_rate = sample_rate
        self.duration_seconds = duration_seconds

    async def synthesize(self, text: str, profile: VoiceProfile) -> bytes:
        """
        Creates a valid standard PCM WAV file buffer.
        """
        buffer = io.BytesIO()
        num_samples = int(self.sample_rate * self.duration_seconds)

        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(1)      # Mono
            wav_file.setsampwidth(2)      # 16-bit
            wav_file.setframerate(self.sample_rate)

            # Generate low-amplitude tone based on profile pitch
            freq = max(100, min(1000, profile.pitch * 10))
            samples = []
            for i in range(num_samples):
                # Gentle square wave
                val = 1000 if (i * freq // self.sample_rate) % 2 == 0 else -1000
                samples.append(val)

            raw_data = struct.pack(f"<{len(samples)}h", *samples)
            wav_file.writeframes(raw_data)

        return buffer.getvalue()
