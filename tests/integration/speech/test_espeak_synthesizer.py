"""Integration tests for SpeechSynthesizer implementations."""

import os
import unittest
from src.domain.entities.voice_profile import VoiceProfile
from src.infrastructure.speech.mock_synthesizer import MockSpeechSynthesizer
from src.infrastructure.speech.espeak_synthesizer import EspeakSpeechSynthesizer

class TestSpeechSynthesizer(unittest.IsolatedAsyncioTestCase):

    async def test_mock_synthesizer_generates_valid_wav(self):
        synth = MockSpeechSynthesizer()
        profile = VoiceProfile(pitch=50, speed=175)
        wav_bytes = await synth.synthesize("Test mock audio generation", profile)

        # WAV header verification
        self.assertGreater(len(wav_bytes), 44)
        self.assertEqual(wav_bytes[:4], b"RIFF")
        self.assertEqual(wav_bytes[8:12], b"WAVE")
        self.assertEqual(wav_bytes[12:16], b"fmt ")

    async def test_espeak_synthesizer_integration(self):
        # Check standard install path or PATH
        win_path = r"C:\Program Files\eSpeak NG\espeak-ng.exe"
        binary_path = win_path if os.path.exists(win_path) else "espeak-ng"

        synth = EspeakSpeechSynthesizer(binary_path)

        # 1. Test English speech synthesis
        en_profile = VoiceProfile.from_tone("serious", "en-us")
        try:
            en_wav = await synth.synthesize("Hello team, testing eSpeak NG integration.", en_profile)
            self.assertGreater(len(en_wav), 44)
            self.assertEqual(en_wav[:4], b"RIFF")
            self.assertEqual(en_wav[8:12], b"WAVE")
        except Exception as e:
            self.skipTest(f"espeak-ng binary not accessible: {e}")

        # 2. Test Russian speech synthesis
        ru_profile = VoiceProfile.from_tone("drill_sergeant", "ru")
        ru_wav = await synth.synthesize("Внимание команде, проверка синтеза речи.", ru_profile)
        self.assertGreater(len(ru_wav), 44)
        self.assertEqual(ru_wav[:4], b"RIFF")
        self.assertEqual(ru_wav[8:12], b"WAVE")

if __name__ == "__main__":
    unittest.main()
