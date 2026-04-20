import subprocess
import tempfile
import os
from openai import OpenAI


class OpenAITTS:
    def __init__(self, api_key: str, voice: str = "nova", model: str = "tts-1"):
        self.client = OpenAI(api_key=api_key)
        self.voice = voice
        self.model = model

    def synthesize(self, text: str) -> tuple[bytes, str]:
        resp = self.client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text,
        )
        return resp.content, "audio/mpeg"

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
