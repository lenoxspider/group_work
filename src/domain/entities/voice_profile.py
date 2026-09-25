"""
Voice profile domain entity.

What it does:
- Models speech synthesis parameters (voice name, language, speed, pitch, tone).
- Applies tone presets (serious, drill_sergeant, deadpan, friendly).
- Provides deterministic per-user pitch and speed offsets.

What it does NOT do:
- Does NOT execute binaries or subprocesses.
- Does NOT interact with Discord APIs.
"""

from dataclasses import dataclass
from typing import Optional
from src.domain.errors import ValidationError

VALID_TONES = {"serious", "drill_sergeant", "deadpan", "friendly"}

@dataclass
class VoiceProfile:
    """Represents a speech synthesis configuration."""
    voice_name: str = "en-us"
    speed: int = 175          # Words per minute (80 to 450)
    pitch: int = 50          # Base pitch (0 to 99)
    tone: str = "serious"
    variant: Optional[str] = None

    def __post_init__(self):
        if not self.voice_name.strip():
            raise ValidationError("Voice name cannot be empty.")
        if self.tone not in VALID_TONES:
            raise ValidationError(f"Invalid tone '{self.tone}'. Valid tones: {', '.join(sorted(VALID_TONES))}")
        self.speed = max(80, min(450, self.speed))
        self.pitch = max(0, min(99, self.pitch))

    @classmethod
    def from_tone(cls, tone: str = "serious", language: str = "en-us") -> "VoiceProfile":
        """Factory creating a profile customized for a specified tone."""
        clean_tone = tone.lower().strip()
        clean_lang = "ru" if language.lower().strip().startswith("ru") else "en-us"

        if clean_tone == "drill_sergeant":
            # Fast, deep, commanding
            return cls(voice_name=clean_lang, speed=195, pitch=35, tone="drill_sergeant", variant="m3")
        elif clean_tone == "deadpan":
            # Flat, slow, monotonous
            return cls(voice_name=clean_lang, speed=145, pitch=25, tone="deadpan", variant=None)
        elif clean_tone == "friendly":
            # Upbeat, slightly higher pitch
            return cls(voice_name=clean_lang, speed=165, pitch=65, tone="friendly", variant="f2")
        else:
            # Default serious: clear, authoritative, neutral
            return cls(voice_name=clean_lang, speed=175, pitch=50, tone="serious", variant=None)

    def with_user_offset(self, user_id: str) -> "VoiceProfile":
        """
        Derives a deterministic variation so each member has a unique vocal signature.
        """
        try:
            numeric_seed = int(user_id)
        except ValueError:
            numeric_seed = sum(ord(c) for c in user_id)

        pitch_offset = (numeric_seed % 31) - 15   # -15 to +15
        speed_offset = (numeric_seed % 21) - 10   # -10 to +10

        new_pitch = max(10, min(85, self.pitch + pitch_offset))
        new_speed = max(110, min(240, self.speed + speed_offset))

        return VoiceProfile(
            voice_name=self.voice_name,
            speed=new_speed,
            pitch=new_pitch,
            tone=self.tone,
            variant=self.variant
        )
