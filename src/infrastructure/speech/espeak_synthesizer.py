"""
eSpeak-NG speech synthesizer implementation.

What it does:
- Executes the espeak-ng binary via async subprocess.
- Maps VoiceProfile (speed, pitch, voice_name, variant) to command-line flags.
- Returns raw WAV audio bytes.

What it does NOT do:
- Does NOT contain business rules or Discord API interactions.
"""

import os
import tempfile
import asyncio
import logging
from src.domain.entities.voice_profile import VoiceProfile
from src.domain.interfaces.speech_synthesizer import SpeechSynthesizer
from src.domain.errors import ExternalServiceError

logger = logging.getLogger("infrastructure.speech.espeak")

class EspeakSpeechSynthesizer(SpeechSynthesizer):
    """Subprocess adapter for eSpeak NG text-to-speech engine."""

    def __init__(self, binary_path: str):
        self.binary_path = binary_path

    async def synthesize(self, text: str, profile: VoiceProfile) -> bytes:
        """
        Invokes espeak-ng to synthesize text into WAV audio.
        """
        # Build voice specifier (e.g. 'en-us+m3' or 'ru')
        voice_arg = profile.voice_name
        if profile.variant:
            voice_arg = f"{profile.voice_name}+{profile.variant}"

        # Create temporary file for wave output
        temp_wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        temp_wav_path = temp_wav.name
        temp_wav.close()

        cmd = [
            self.binary_path,
            "-b", "1",
            "-v", voice_arg,
            "-s", str(profile.speed),
            "-p", str(profile.pitch),
            "-w", temp_wav_path
        ]

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(input=text.encode("utf-8")),
                timeout=15.0
            )

            if process.returncode != 0:
                err_msg = stderr.decode(errors="replace").strip()
                logger.error("espeak-ng failed with code %d: %s", process.returncode, err_msg)
                raise ExternalServiceError(f"eSpeak NG synthesis failed: {err_msg}")

            if not os.path.exists(temp_wav_path) or os.path.getsize(temp_wav_path) == 0:
                raise ExternalServiceError("eSpeak NG produced an empty or missing audio file.")

            with open(temp_wav_path, "rb") as f:
                wav_bytes = f.read()

            return wav_bytes
        except FileNotFoundError as e:
            logger.error("eSpeak NG binary not found at '%s': %s", self.binary_path, e)
            raise ExternalServiceError(
                f"eSpeak NG binary not found at '{self.binary_path}'. Please check your configuration."
            ) from e
        finally:
            if os.path.exists(temp_wav_path):
                try:
                    os.remove(temp_wav_path)
                except OSError:
                    pass
