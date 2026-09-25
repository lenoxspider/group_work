"""
Audio deliverer interface.

What it does:
- Defines the abstract contract for delivering synthesized audio to a channel or user.

What it does NOT do:
- Does NOT perform voice synthesis.
- Does NOT implement specific Discord API calls.
"""

from typing import Protocol, Any, Optional

class AudioDeliverer(Protocol):
    """Abstract interface for audio output delivery (attachment or voice channel)."""

    async def deliver(
        self,
        target: Any,
        audio_bytes: bytes,
        filename: str = "announcement.wav",
        content: Optional[str] = None,
        embed: Optional[Any] = None
    ) -> Any:
        """
        Delivers synthesized audio to the specified target.

        Args:
            target: Discord channel or interaction target.
            audio_bytes: Raw audio byte payload.
            filename: Name for the attachment.
            content: Optional message text caption.
            embed: Optional rich presentation embed.
        """
        ...
