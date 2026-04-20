from typing import Protocol


class TTSClient(Protocol):
    def speak(self, text: str) -> None:
        """Synchronously speak `text`. Must block until playback is finished."""
        ...

    def synthesize(self, text: str) -> tuple[bytes, str]:
        """Return (audio_bytes, mime_type) without playing. Used by /voice endpoint."""
        ...
