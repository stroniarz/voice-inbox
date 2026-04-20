"""Config loading — defaults + example.yaml + edge cases."""
from pathlib import Path

from voice_inbox.config import (
    load_config, ServerConfig, CCConfig, AskConfig, VoiceConfig,
)

ROOT = Path(__file__).resolve().parent.parent


def test_example_yaml_loads_with_defaults():
    cfg = load_config(ROOT / "config.example.yaml")
    assert cfg.server.enabled is False
    assert cfg.server.port == 8765
    assert cfg.cc.enabled is False
    assert cfg.cc.stop_min_duration_seconds == 30
    assert cfg.cc.summary_enabled is False
    assert cfg.ask.enabled is False
    assert cfg.ask.history_hours == 24
    assert cfg.voice.enabled is False
    assert cfg.voice.stt["provider"] == "whisper_local"


def test_minimal_yaml(tmp_path):
    (tmp_path / "min.yaml").write_text("""
language: en
llm:
  provider: anthropic
  model: claude-haiku-4-5-20251001
tts:
  provider: say
  voice: Samantha
sources:
  linear:
    enabled: false
""")
    cfg = load_config(tmp_path / "min.yaml")
    assert cfg.language == "en"
    assert cfg.server == ServerConfig()  # defaults
    assert cfg.cc == CCConfig()
    assert cfg.ask == AskConfig()
    assert cfg.voice.enabled is False
    assert cfg.voice.stt == {}  # no stt config


def test_yaml_with_all_sections(tmp_path):
    (tmp_path / "full.yaml").write_text("""
language: pl
llm:
  provider: anthropic
  model: claude-haiku-4-5-20251001
tts:
  provider: say
server:
  enabled: true
  port: 9000
claude_code:
  enabled: true
  summary_enabled: true
  summary_min_duration_seconds: 120
  cooldown_seconds: 30
ask:
  enabled: true
  history_hours: 48
  max_tokens: 600
voice:
  enabled: true
  stt:
    provider: whisper_local
    model: medium
sources:
  linear:
    enabled: false
""")
    cfg = load_config(tmp_path / "full.yaml")
    assert cfg.server.enabled is True
    assert cfg.server.port == 9000
    assert cfg.cc.enabled is True
    assert cfg.cc.summary_enabled is True
    assert cfg.cc.summary_min_duration_seconds == 120
    assert cfg.cc.cooldown_seconds == 30
    assert cfg.ask.enabled is True
    assert cfg.ask.history_hours == 48
    assert cfg.ask.max_tokens == 600
    assert cfg.voice.enabled is True
    assert cfg.voice.stt["model"] == "medium"
