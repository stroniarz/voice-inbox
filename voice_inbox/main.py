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

    if not adapters:
        logging.error("No adapters enabled. Exiting.")
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
