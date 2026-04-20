import io
import os
from openai import OpenAI


class OpenAISTT:
    """
    OpenAI Whisper API.

    Config:
      provider: openai
      model: whisper-1
      api_key_env: OPENAI_API_KEY
    """

    def __init__(self, cfg: dict):
        env = cfg.get("api_key_env", "OPENAI_API_KEY")
        api_key = os.environ.get(env)
        if not api_key:
            raise RuntimeError(f"OpenAI STT: env {env} not set")
        self.client = OpenAI(api_key=api_key)
        self.model = cfg.get("model", "whisper-1")

    def transcribe(self, audio_bytes: bytes, filename: str = "audio.webm",
                   language: str | None = None) -> str:
        buf = io.BytesIO(audio_bytes)
        buf.name = filename
        kwargs = {"model": self.model, "file": buf}
        if language:
            kwargs["language"] = language
        r = self.client.audio.transcriptions.create(**kwargs)
        return (r.text or "").strip()
