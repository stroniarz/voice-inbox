from typing import Protocol


class TTSClient(Protocol):
    def speak(self, text: str) -> None:
        """Synchronously speak `text`. Must block until playback is finished."""
        ...
