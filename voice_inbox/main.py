import argparse
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from .config import load_config
from .dedup import DedupStore
from .llm import make_llm
from .summarize import Summarizer
from .tts import make_tts
from .tts.worker import TTSWorker
from .adapters.linear import LinearAdapter
from .adapters.slack import SlackAdapter
from .cc import CCHandler, TranscriptSummarizer
from .ask import AskHandler
from .channels_bridge import ChannelsBridge
from .channels_permissions import PermissionsBroker
from .server import make_app, serve_in_thread
from .stt import make_stt


ADAPTERS = {
    "linear": LinearAdapter,
    "slack": SlackAdapter,
}


def build_adapters(cfg, store):
    adapters = []
    for src in cfg.sources:
        if not src.enabled:
            continue
        cls = ADAPTERS.get(src.name)
        if not cls:
            logging.warning("Unknown source: %s", src.name)
            continue
        try:
            adapters.append(cls(src, store, language=cfg.language))
            logging.info("Enabled adapter: %s", src.name)
        except Exception as e:
            logging.error("Adapter %s init failed: %s", src.name, e)
    return adapters


def digest_worker(store, summarizer, tts_worker, interval, stop_flag, window_minutes):
    logging.info("Digest worker: every %ss, window %smin", interval, window_minutes)
    for _ in range(interval):
        if stop_flag["flag"]:
            return
        time.sleep(1)
    while not stop_flag["flag"]:
        try:
            events = store.fetch_undigested(since_minutes=window_minutes)
            if not events:
                logging.info("Digest: no events, skipping")
            elif len(events) < 3:
                logging.info("Digest: only %d event(s), live already covered, skipping", len(events))
                store.mark_digested([e["id"] for e in events])
            else:
                logging.info("Digest: %d events", len(events))
                try:
                    text = summarizer.digest(events)
                except Exception as e:
                    logging.error("Digest summarize failed: %s", e)
                    text = None
                if text:
                    logging.info("Digest: %s", text)
                    tts_worker.enqueue(text, tag="default")
                    store.mark_digested([e["id"] for e in events])
                else:
                    logging.info("Digest: LLM returned SKIP")
        except Exception as e:
            logging.error("Digest worker failed: %s", e)
        for _ in range(interval):
            if stop_flag["flag"]:
                return
            time.sleep(1)


def run(config_path: Path) -> None:
    cfg = load_config(config_path)
    store = DedupStore(cfg.db_path)

    llm = make_llm(cfg.llm)
    logging.info("LLM: %s / %s", cfg.llm.get("provider", "anthropic"), cfg.llm.get("model"))

    tts_configs = cfg.tts
    if "default" in tts_configs or "critical" in tts_configs:
        default_cfg = tts_configs.get("default") or {}
        critical_cfg = tts_configs.get("critical") or default_cfg
    else:
        default_cfg = tts_configs
        critical_cfg = tts_configs
    clients = {"default": make_tts(default_cfg)}
    if critical_cfg and critical_cfg is not default_cfg:
        clients["critical"] = make_tts(critical_cfg)
    logging.info(
        "TTS default: %s, critical: %s",
        default_cfg.get("provider", "say"),
        critical_cfg.get("provider", "say") if "critical" in clients else "(same as default)",
    )
    tts_worker = TTSWorker(clients)

    summarizer = Summarizer(llm, language=cfg.language)
    logging.info("Language: %s", cfg.language)
    adapters = build_adapters(cfg, store)

    if cfg.server.enabled:
        cc_handler = None
        if cfg.cc.enabled:
            transcript_summarizer = None
            if cfg.cc.summary_enabled:
                transcript_summarizer = TranscriptSummarizer(llm, language=cfg.language)
                logging.info("CC transcript summarizer enabled (min=%ss)",
                             cfg.cc.summary_min_duration_seconds)
            cc_handler = CCHandler(
                store, tts_worker, language=cfg.language,
                stop_min_duration_seconds=cfg.cc.stop_min_duration_seconds,
                cooldown_seconds=cfg.cc.cooldown_seconds,
                ignore_events=cfg.cc.ignore_events,
                transcript_summarizer=transcript_summarizer,
                summary_min_duration_seconds=cfg.cc.summary_min_duration_seconds,
            )
            logging.info("Claude Code adapter enabled (cooldown=%ss)",
                         cfg.cc.cooldown_seconds)

        ask_handler = None
        if cfg.ask.enabled:
            ask_handler = AskHandler(
                llm, store, language=cfg.language,
                history_hours=cfg.ask.history_hours,
                max_events=cfg.ask.max_events,
                max_tokens=cfg.ask.max_tokens,
            )
            logging.info("Ask handler enabled (history=%sh)",
                         cfg.ask.history_hours)

        stt_client = None
        public_dir = None
        if cfg.voice.enabled:
            if ask_handler is None:
                logging.warning("voice.enabled=true but ask.enabled=false — voice requires ask")
            else:
                try:
                    stt_client = make_stt(cfg.voice.stt)
                    logging.info("STT: %s", cfg.voice.stt.get("provider", "whisper_local"))
                except Exception as e:
                    logging.error("STT init failed: %s", e)
            if cfg.voice.serve_public:
                public_dir = Path(__file__).resolve().parent.parent / "public"
                if not public_dir.is_dir():
                    public_dir = None
                    logging.warning("public/ directory not found — PWA not served")

        tts_for_voice = clients.get("default")

        channels_bridge = ChannelsBridge()
        permissions_broker = PermissionsBroker()
        logging.info(
            "Channels bridge + permissions enabled; archive_replies=%s archive_permissions=%s lang=%s",
            cfg.channels.archive_replies,
            cfg.channels.archive_permissions,
            cfg.channels.permissions_language,
        )

        app = make_app(
            cc_handler=cc_handler,
            ask_handler=ask_handler,
            store=store,
            stt_client=stt_client,
            tts_client=tts_for_voice,
            public_dir=public_dir,
            stt_language=cfg.voice.language,
            channels_bridge=channels_bridge,
            tts_worker=tts_worker,
            archive_replies=cfg.channels.archive_replies,
            permissions_broker=permissions_broker,
            archive_permissions=cfg.channels.archive_permissions,
            permissions_language=cfg.channels.permissions_language,
        )
        serve_in_thread(app, cfg.server.host, cfg.server.port)
        logging.info("HTTP server: http://%s:%d", cfg.server.host, cfg.server.port)
        if public_dir:
            logging.info("PWA served at http://%s:%d/", cfg.server.host, cfg.server.port)

    if not adapters and not cfg.cc.enabled:
        logging.error("No adapters or push receivers enabled. Exiting.")
        sys.exit(1)

    stop = {"flag": False}

    def handle_sig(*_):
        logging.info("Stopping...")
        stop["flag"] = True

    signal.signal(signal.SIGINT, handle_sig)
    signal.signal(signal.SIGTERM, handle_sig)

    digest_window_min = max(1, cfg.digest_interval_seconds // 60)
    digest_thread = threading.Thread(
        target=digest_worker,
        args=(store, summarizer, tts_worker, cfg.digest_interval_seconds, stop, digest_window_min),
        daemon=True,
    )
    digest_thread.start()

    logging.info(
        "Voice Inbox running. Poll: %ss, Digest: %ss",
        cfg.poll_interval_seconds,
        cfg.digest_interval_seconds,
    )

    while not stop["flag"]:
        for adapter in adapters:
            try:
                for event in adapter.poll():
                    store.archive_event(
                        event.source, event.external_id, event.author,
                        event.short, event.title, event.body,
                        project=event.project,
                    )
                    line = f"{event.source}, {event.short}"
                    tag = "critical" if event.priority in (1, 2) else "default"
                    logging.info("[%s] say (%s): %s", event.source, tag, line)
                    tts_worker.enqueue(line, tag=tag)
            except Exception as e:
                logging.error("Adapter %s poll failed: %s", adapter.name, e)

        for _ in range(cfg.poll_interval_seconds):
            if stop["flag"]:
                break
            time.sleep(1)


def main():
    parser = argparse.ArgumentParser(prog="voice-inbox")
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config.yaml"),
        help="Path to config.yaml",
    )
    parser.add_argument("--log-level", default="INFO")
    args = parser.parse_args()

    logging.basicConfig(
        level=args.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    run(args.config)


if __name__ == "__main__":
    main()
