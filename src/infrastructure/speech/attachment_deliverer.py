"""
Attachment audio deliverer.

What it does:
- Wraps synthesized audio bytes into a discord.File attachment.
- Dispatches attachment to a Discord channel or interaction.

What it does NOT do:
- Does NOT connect to voice channels or manage audio queues (Phase 2).
"""

import io
from typing import Any, Optional
import discord
from src.domain.interfaces.audio_deliverer import AudioDeliverer

class AttachmentAudioDeliverer(AudioDeliverer):
    """Delivers synthesized audio as a downloadable Discord file attachment."""

    async def deliver(
        self,
        target: Any,
        audio_bytes: bytes,
        filename: str = "announcement.wav",
        content: Optional[str] = None,
        embed: Optional[discord.Embed] = None
    ) -> Any:
        """
        Sends audio attachment and optional embed to destination.
        """
        file_obj = discord.File(io.BytesIO(audio_bytes), filename=filename)

        if hasattr(target, "followup"):
            # Discord Interaction
            return await target.followup.send(content=content, file=file_obj, embed=embed)
        elif hasattr(target, "send"):
            # Discord TextChannel, Thread, or Member DM
            return await target.send(content=content, file=file_obj, embed=embed)
        else:
            raise TypeError(f"Unsupported delivery target: {type(target)}")
