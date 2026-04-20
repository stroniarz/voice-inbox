from .base import STTClient


def make_stt(cfg: dict) -> STTClient:
    provider = (cfg or {}).get("provider", "whisper_local")
    if provider == "whisper_local":
        from .whisper_local import WhisperLocalSTT
        return WhisperLocalSTT(cfg)
    if provider == "openai":
        from .openai_stt import OpenAISTT
        return OpenAISTT(cfg)
    raise ValueError(f"Unknown STT provider: {provider}")


__all__ = ["make_stt", "STTClient"]
