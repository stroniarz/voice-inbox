import subprocess


class SayTTS:
    def __init__(self, voice: str = "Samantha", rate: int = 180):
        self.voice = voice
        self.rate = rate

    def speak(self, text: str) -> None:
        subprocess.run(
            ["say", "-v", self.voice, "-r", str(self.rate), text],
            check=False,
        )
