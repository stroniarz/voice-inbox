import subprocess
import tempfile
import os
from openai import OpenAI


class OpenAITTS:
    def __init__(self, api_key: str, voice: str = "nova", model: str = "tts-1"):
        self.client = OpenAI(api_key=api_key)
        self.voice = voice
        self.model = model

    def speak(self, text: str) -> None:
        resp = self.client.audio.speech.create(
            model=self.model,
            voice=self.voice,
            input=text,
        )
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            f.write(resp.content)
            path = f.name
        try:
            subprocess.run(["afplay", path], check=False)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass
