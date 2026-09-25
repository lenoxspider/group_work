"""
Squid Game Guard and Doll speech taxonomy.

What it does:
- Encapsulates cold, emotionless voice line templates for Masked Guards and the Doll.
- Provides static profiles tuned specifically for eSpeak-NG's robotic flat tone (-s 110, -p 15).

What it does NOT do:
- Does NOT execute synthesis or communicate with Discord.
"""

from src.domain.entities.voice_profile import VoiceProfile

GUARD_PROFILE = VoiceProfile(
    voice_name="en-us",
    speed=110,
    pitch=15,
    variant=None,
    tone="guard"
)

DOLL_PROFILE = VoiceProfile(
    voice_name="ko",
    speed=125,
    pitch=60,
    variant=None,
    tone="doll"
)

class GuardVoiceLines:
    """Predefined voice scripts for Squid Game accountability events."""

    @staticmethod
    def elimination(spoken_number: str) -> str:
        """Iconic elimination announcement."""
        return f"Player {spoken_number}. Eliminated."

    @staticmethod
    def game_announcement(game_name: str) -> str:
        """Announcement before game begins."""
        return f"Attention, players. The next game is {game_name}. Please proceed to the game area."

    @staticmethod
    def movement_detected() -> str:
        """Warning/kill trigger in Red Light Green Light."""
        return "Movement detected. Player eliminated."

    @staticmethod
    def red_light() -> str:
        """Red light trigger."""
        return "Red light. Remain still."

    @staticmethod
    def green_light_korean() -> str:
        """Iconic doll chant in Korean."""
        return "무궁화 꽃이 피었습니다."

    @staticmethod
    def green_light_english() -> str:
        """Alternative English chant."""
        return "Green light. Advance now."

    @staticmethod
    def prize_update() -> str:
        """Prize pot accumulation announcement."""
        return "The prize pool has increased."

    @staticmethod
    def survival(spoken_number: str) -> str:
        """Player survival confirmation."""
        return f"Player {spoken_number}. Survived."
