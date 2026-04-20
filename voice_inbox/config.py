from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class SourceConfig:
    name: str
    enabled: bool
    options: dict = field(default_factory=dict)


@dataclass
class ServerConfig:
    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class CCConfig:
    enabled: bool = False
    stop_min_duration_seconds: int = 30
    cooldown_seconds: int = 60
    ignore_events: tuple[str, ...] = ()


@dataclass
class AskConfig:
    enabled: bool = False
    history_hours: int = 24
    max_events: int = 80
    max_tokens: int = 400


@dataclass
class Config:
    poll_interval_seconds: int
    digest_interval_seconds: int
    language: str
    llm: dict
    tts: dict
    db_path: Path
    sources: list[SourceConfig]
    server: ServerConfig
    cc: CCConfig
    ask: AskConfig


def load_config(path: Path) -> Config:
    raw = yaml.safe_load(path.read_text())

    sources = []
    for name, src in (raw.get("sources") or {}).items():
        sources.append(
            SourceConfig(
                name=name,
                enabled=bool(src.get("enabled", False)),
                options=src,
            )
        )

    state_cfg = raw.get("state", {})
    db_path = Path(state_cfg.get("db_path", "~/.voice-inbox/state.db")).expanduser()
    db_path.parent.mkdir(parents=True, exist_ok=True)

    server_raw = raw.get("server") or {}
    server = ServerConfig(
        enabled=bool(server_raw.get("enabled", False)),
        host=str(server_raw.get("host", "127.0.0.1")),
        port=int(server_raw.get("port", 8765)),
    )

    cc_raw = raw.get("claude_code") or {}
    cc = CCConfig(
        enabled=bool(cc_raw.get("enabled", False)),
        stop_min_duration_seconds=int(cc_raw.get("stop_min_duration_seconds", 30)),
        cooldown_seconds=int(cc_raw.get("cooldown_seconds", 60)),
        ignore_events=tuple(cc_raw.get("ignore_events") or ()),
    )

    ask_raw = raw.get("ask") or {}
    ask = AskConfig(
        enabled=bool(ask_raw.get("enabled", False)),
        history_hours=int(ask_raw.get("history_hours", 24)),
        max_events=int(ask_raw.get("max_events", 80)),
        max_tokens=int(ask_raw.get("max_tokens", 400)),
    )

    return Config(
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 60)),
        digest_interval_seconds=int(raw.get("digest_interval_seconds", 3600)),
        language=(raw.get("language") or "pl").lower(),
        llm=raw.get("llm") or {},
        tts=raw.get("tts") or {},
        db_path=db_path,
        sources=sources,
        server=server,
        cc=cc,
        ask=ask,
    )
