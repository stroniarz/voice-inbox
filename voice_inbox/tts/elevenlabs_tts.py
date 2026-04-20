import subprocess
import tempfile
import os
import requests


class ElevenLabsTTS:
    def __init__(self, api_key: str, voice_id: str, model: str = "eleven_turbo_v2_5",
                 speed: float = 1.0, stability: float = 0.5, similarity_boost: float = 0.75):
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.speed = speed
        self.stability = stability
        self.similarity_boost = similarity_boost

    def synthesize(self, text: str) -> tuple[bytes, str]:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
        r = requests.post(
            url,
            headers={
                "xi-api-key": self.api_key,
                "accept": "audio/mpeg",
                "content-type": "application/json",
            },
            json={
                "text": text,
                "model_id": self.model,
                "voice_settings": {
                    "stability": self.stability,
                    "similarity_boost": self.similarity_boost,
                    "speed": self.speed,
                },
            },
            timeout=60,
        )
        r.raise_for_status()
        return r.content, "audio/mpeg"

    def speak(self, text: str) -> None:
        audio, _ = self.synthesize(text)
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(audio)
            path = f.name
        try:
            subprocess.run(["afplay", path], check=False)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
