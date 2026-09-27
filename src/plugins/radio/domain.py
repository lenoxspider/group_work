"""Radio domain - track model and radio-specific errors."""

from dataclasses import dataclass


class RadioError(Exception):
    """Base radio domain error."""


class ResolutionError(RadioError):
    """A source could not be resolved to a playable audio stream."""


class NotInVoiceChannel(RadioError):
    """The command was invoked by a user not connected to a voice channel."""


class NoActivePlayer(RadioError):
    """No active player exists for the guild."""


@dataclass(frozen=True)
class Track:
    """A resolvable audio track queued for playback."""

    url: str
    title: str
    duration: int
    requester_id: str
    stream_url: str
    webpage_url: str = ""