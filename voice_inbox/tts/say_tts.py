import subprocess
import tempfile
from pathlib import Path


class SayTTS:
    def __init__(self, voice: str = "Samantha", rate: int = 180):
        self.voice = voice
        self.rate = rate

    def speak(self, text: str) -> None:
        subprocess.run(
            ["say", "-v", self.voice, "-r", str(self.rate), text],
            check=False,
        )

    def synthesize(self, text: str) -> tuple[bytes, str]:
        """Generate WAV via `say -o`; returns (bytes, mime)."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            path = f.name
        try:
            subprocess.run(
                ["say", "-v", self.voice, "-r", str(self.rate),
                 "-o", path, "--file-format=WAVE",
                 "--data-format=LEI16@22050", text],
                check=False,
            )
            data = Path(path).read_bytes()
            return data, "audio/wav"
        finally:
            try:
                Path(path).unlink()
            except OSError:
                pass
