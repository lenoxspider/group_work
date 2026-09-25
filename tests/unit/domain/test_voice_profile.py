"""Unit tests for VoiceProfile domain entity."""

import unittest
from src.domain.entities.voice_profile import VoiceProfile
from src.domain.errors import ValidationError

class TestVoiceProfile(unittest.TestCase):

    def test_default_profile(self):
        profile = VoiceProfile()
        self.assertEqual(profile.voice_name, "en-us")
        self.assertEqual(profile.speed, 175)
        self.assertEqual(profile.pitch, 50)
        self.assertEqual(profile.tone, "serious")

    def test_empty_voice_name_raises_error(self):
        with self.assertRaises(ValidationError):
            VoiceProfile(voice_name="  ")

    def test_invalid_tone_raises_error(self):
        with self.assertRaises(ValidationError):
            VoiceProfile(tone="sarcastic")

    def test_speed_and_pitch_clamping(self):
        profile_low = VoiceProfile(speed=10, pitch=-20)
        self.assertEqual(profile_low.speed, 80)
        self.assertEqual(profile_low.pitch, 0)

        profile_high = VoiceProfile(speed=999, pitch=250)
        self.assertEqual(profile_high.speed, 450)
        self.assertEqual(profile_high.pitch, 99)

    def test_from_tone_drill_sergeant(self):
        profile = VoiceProfile.from_tone("drill_sergeant", "en-us")
        self.assertEqual(profile.tone, "drill_sergeant")
        self.assertEqual(profile.variant, "m3")
        self.assertLess(profile.pitch, 40)
        self.assertGreater(profile.speed, 180)

    def test_from_tone_deadpan(self):
        profile = VoiceProfile.from_tone("deadpan", "en-us")
        self.assertEqual(profile.tone, "deadpan")
        self.assertIsNone(profile.variant)
        self.assertLess(profile.speed, 160)
        self.assertLess(profile.pitch, 30)

    def test_from_tone_friendly(self):
        profile = VoiceProfile.from_tone("friendly", "ru")
        self.assertEqual(profile.tone, "friendly")
        self.assertEqual(profile.voice_name, "ru")
        self.assertEqual(profile.variant, "f2")
        self.assertGreater(profile.pitch, 60)

    def test_with_user_offset_deterministic(self):
        base = VoiceProfile.from_tone("serious")
        p1 = base.with_user_offset("123456789")
        p2 = base.with_user_offset("123456789")
        p3 = base.with_user_offset("987654321")

        self.assertEqual(p1.pitch, p2.pitch)
        self.assertEqual(p1.speed, p2.speed)
        # Different members get distinct vocal parameters
        self.assertTrue(p1.pitch != p3.pitch or p1.speed != p3.speed)

if __name__ == "__main__":
    unittest.main()
