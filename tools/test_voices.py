#!/usr/bin/env python3
"""Test ElevenLabs voices — speaks a sample phrase with each preset voice."""
import os
import sys
import time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from voice_inbox.tts.elevenlabs_tts import ElevenLabsTTS

API_KEY = os.environ["ELEVENLABS_API_KEY"]
MODEL = os.environ.get("EL_MODEL", "eleven_turbo_v2_5")

VOICES = [
    ("ThT5KcBeYPX3keUQqHPh", "Dorothy",  "British female"),
    ("JBFqnCBsd6RMkjVDRZzb", "George",   "British male"),
    ("21m00Tcm4TlvDq8ikWAM", "Rachel",   "US female"),
    ("EXAVITQu4vr4xnSDxMaL", "Sarah",    "US female young"),
    ("TxGEqnHWrfWFTfGW9XjX", "Josh",     "US male"),
    ("29vD33N1CtxCmqQRPOHJ", "Drew",     "US male narrator"),
]

SAMPLE_EN = (
    "Hourly briefing. Linear update on Voice Inbox, "
    "status In Progress. Total: one task and one comment."
)
SAMPLE_PL = (
    "Raport z ostatniej godziny. Linear, nowe zadanie Voice Inbox "
    "abstrakcja TTS. Razem: jedno nowe zadanie i jeden komentarz."
)

sample = SAMPLE_PL if os.environ.get("LANG_TEST") == "pl" else SAMPLE_EN

for vid, name, desc in VOICES:
    print(f"\n▶ {name} ({desc}) — {vid}")
    tts = ElevenLabsTTS(api_key=API_KEY, voice_id=vid, model=MODEL)
    try:
        tts.speak(f"{name}. {sample}")
    except Exception as e:
        print(f"  FAILED: {e}")
    time.sleep(0.5)

print("\nDone.")
