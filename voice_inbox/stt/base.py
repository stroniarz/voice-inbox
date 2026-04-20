from typing import Protocol


class STTClient(Protocol):
    def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm",
                   language: str | None = None) -> str:
        ...
