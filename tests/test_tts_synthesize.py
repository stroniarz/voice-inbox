"""TTS synthesize() — returns (bytes, mime) for /voice endpoint."""
import platform

import pytest

from voice_inbox.tts.say_tts import SayTTS


@pytest.mark.skipif(platform.system() != "Darwin",
                    reason="say command is macOS-only")
def test_say_synthesize_produces_wav():
    tts = SayTTS(voice="Samantha", rate=160)
    audio, mime = tts.synthesize("Hello test")
    assert mime == "audio/wav"
    # WAV header: RIFF....WAVE
    assert audio[:4] == b"RIFF"
    assert audio[8:12] == b"WAVE"
    # Reasonable size for ~1s speech at 22050Hz 16-bit mono
    assert len(audio) > 1000


@pytest.mark.skipif(platform.system() != "Darwin",
                    reason="say command is macOS-only")
def test_say_synthesize_handles_empty_text():
    tts = SayTTS(voice="Samantha", rate=160)
    audio, mime = tts.synthesize("")
    assert mime == "audio/wav"
    # Empty input still produces a tiny WAV header
    assert audio[:4] == b"RIFF"
