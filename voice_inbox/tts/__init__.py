import os
from .base import TTSClient


def make_tts(cfg: dict) -> TTSClient:
    provider = (cfg.get("provider") or "say").lower()

    if provider == "say":
        from .say_tts import SayTTS
        return SayTTS(voice=cfg.get("voice", "Samantha"), rate=int(cfg.get("rate", 180)))

    api_key_env = cfg.get("api_key_env")
    api_key = os.environ.get(api_key_env) if api_key_env else None

    if provider == "elevenlabs":
        if not api_key:
            raise ValueError(f"ElevenLabs requires env {api_key_env or 'ELEVENLABS_API_KEY'}")
        from .elevenlabs_tts import ElevenLabsTTS
        return ElevenLabsTTS(
            api_key=api_key,
            voice_id=cfg["voice_id"],
            model=cfg.get("model", "eleven_turbo_v2_5"),
            speed=float(cfg.get("speed", 1.0)),
            stability=float(cfg.get("stability", 0.5)),
            similarity_boost=float(cfg.get("similarity_boost", 0.75)),
        )

    if provider == "openai":
        if not api_key:
            raise ValueError(f"OpenAI TTS requires env {api_key_env or 'OPENAI_API_KEY'}")
        from .openai_tts import OpenAITTS
        return OpenAITTS(
            api_key=api_key,
            voice=cfg.get("voice", "nova"),
            model=cfg.get("model", "tts-1"),
        )

    raise ValueError(f"Unknown TTS provider: {provider}")
