from dataclasses import dataclass, field
from pathlib import Path
import yaml


@dataclass
class SourceConfig:
    name: str
    enabled: bool
    options: dict = field(default_factory=dict)


@dataclass
class Config:
    poll_interval_seconds: int
    digest_interval_seconds: int
    language: str
    llm: dict
    tts: dict
    db_path: Path
    sources: list[SourceConfig]


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

    return Config(
        poll_interval_seconds=int(raw.get("poll_interval_seconds", 60)),
        digest_interval_seconds=int(raw.get("digest_interval_seconds", 3600)),
        language=(raw.get("language") or "pl").lower(),
        llm=raw.get("llm") or {},
        tts=raw.get("tts") or {},
        db_path=db_path,
        sources=sources,
    )
