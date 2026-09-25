"""
Voice speech synthesis Discord slash commands.

What it does:
- Exposes /say slash command for generating speech attachments with custom tones and languages.
- Invokes VoiceService and AudioDeliverer.

What it does NOT do:
- Does NOT execute binaries directly.
- Does NOT contain synthesis logic.
"""

import logging
from typing import Optional
import discord
from discord import app_commands
from discord.ext import commands

from src.application.services.voice_service import VoiceService
from src.application.dtos.voice_dtos import SynthesizeRequestDTO
from src.domain.interfaces.audio_deliverer import AudioDeliverer
from src.interface.discord_formatters import build_voice_embed
from src.domain.errors import AppError

logger = logging.getLogger("interface.cogs.voice")

class VoiceCog(commands.Cog, name="Voice Synthesis"):
    """Interface adapter for speech synthesis and voice commands."""

    def __init__(
        self,
        bot: commands.Bot,
        voice_service: VoiceService,
        audio_deliverer: AudioDeliverer
    ):
        self.bot = bot
        self.voice_service = voice_service
        self.audio_deliverer = audio_deliverer

    @app_commands.command(name="say", description="Speak arbitrary text aloud into an audio announcement file")
    @app_commands.describe(
        text="The message text to synthesize",
        tone="Tone preset (serious, drill_sergeant, deadpan, friendly)",
        lang="Language code (en-us, ru)"
    )
    @app_commands.choices(tone=[
        app_commands.Choice(name="💼 Serious (Authoritative)", value="serious"),
        app_commands.Choice(name="🪖 Drill Sergeant (Fast & Commanding)", value="drill_sergeant"),
        app_commands.Choice(name="😐 Deadpan (Flat & Monotonous)", value="deadpan"),
        app_commands.Choice(name="😊 Friendly (Upbeat)", value="friendly"),
    ])
    @app_commands.choices(lang=[
        app_commands.Choice(name="🇺🇸 English (US)", value="en-us"),
        app_commands.Choice(name="🇷🇺 Russian", value="ru"),
    ])
    async def say(
        self,
        interaction: discord.Interaction,
        text: str,
        tone: Optional[app_commands.Choice[str]] = None,
        lang: Optional[app_commands.Choice[str]] = None
    ):
        await interaction.response.defer()
        selected_tone = tone.value if tone else "serious"
        selected_lang = lang.value if lang else "en-us"

        dto = SynthesizeRequestDTO(
            text=text,
            user_id=str(interaction.user.id),
            tone=selected_tone,
            language=selected_lang
        )

        try:
            clip = await self.voice_service.synthesize(dto)
            embed = build_voice_embed(
                transcript=clip.transcript,
                tone=clip.tone,
                language=clip.language,
                author_name=interaction.user.display_name
            )
            await self.audio_deliverer.deliver(
                target=interaction,
                audio_bytes=clip.audio_bytes,
                filename=clip.filename,
                embed=embed
            )
        except AppError as e:
            await interaction.followup.send(f"❌ {e.message}", ephemeral=True)
        except Exception as e:
            logger.error("Failed to synthesize voice message: %s", e, exc_info=True)
            await interaction.followup.send("❌ Internal error during speech synthesis.", ephemeral=True)

async def setup(bot: commands.Bot):
    # Cog is registered in bot.py setup_hook
    pass
