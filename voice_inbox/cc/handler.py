import logging
import threading
import time
from pathlib import Path

from ..i18n import t

logger = logging.getLogger(__name__)


# Hook event → priority tag for TTS routing
PRIORITY_TAG = {
    "Notification": "critical",  # user permission needed
    "Stop": "default",
    "SubagentStop": "default",
}


class CCHandler:
    """
    Receives Claude Code hook payloads (POST /cc-event), generates short
    audio notifications, archives to DedupStore, enqueues to TTSWorker.

    Per-project cooldown prevents Stop spam when CC fires Stop frequently
    on short interactions.

    If a transcript_summarizer is provided, Stop events of long-enough
    sessions trigger a 1-sentence LLM summary of what the agent did
    (replaces generic "session ended" announcement).
    """

    def __init__(self, store, tts_worker, language: str,
                 stop_min_duration_seconds: int = 30,
                 cooldown_seconds: int = 60,
                 ignore_events: tuple[str, ...] = (),
                 transcript_summarizer=None,
                 summary_min_duration_seconds: int = 60):
        self.store = store
        self.tts_worker = tts_worker
        self.language = language
        self.stop_min_duration = stop_min_duration_seconds
        self.cooldown = cooldown_seconds
        self.ignore_events = set(ignore_events)
        self.transcript_summarizer = transcript_summarizer
        self.summary_min_duration = summary_min_duration_seconds
        self._last_announce: dict[str, float] = {}
        self._session_start: dict[str, float] = {}
        self._transcript_paths: dict[str, str] = {}
        self._lock = threading.Lock()

    def __call__(self, payload: dict) -> None:
        event = payload.get("hook_event_name") or payload.get("event")
        cwd = payload.get("cwd") or payload.get("project_dir") or ""
        project = Path(cwd).name or "?"
        session_id = payload.get("session_id", "")

        if not event or event in self.ignore_events:
            return

        # Track session start + transcript path (we see UserPromptSubmit /
        # PreToolUse before Stop)
        if event in ("UserPromptSubmit", "PreToolUse") and session_id:
            self._session_start.setdefault(session_id, time.time())
            tpath = payload.get("transcript_path")
            if tpath:
                self._transcript_paths[session_id] = tpath
            return

        if event == "Stop":
            # Transcript path from Stop payload takes precedence if present
            tpath = payload.get("transcript_path") or self._transcript_paths.pop(session_id, None)
            short = self._handle_stop(project, session_id, tpath)
        elif event == "SubagentStop":
            short = t(self.language, "cc_subagent_stop", project=project)
        elif event == "Notification":
            message = (payload.get("message") or "").strip() or "wymaga uwagi"
            short = t(self.language, "cc_notification",
                      project=project, message=message)
        else:
            return

        if short is None:
            return

        # Cooldown per project to avoid spam
        key = f"{event}:{project}"
        now = time.time()
        with self._lock:
            last = self._last_announce.get(key, 0.0)
            if now - last < self.cooldown:
                logger.info("CC: cooldown skip %s for %s", event, project)
                return
            self._last_announce[key] = now

        external_id = f"{event}:{session_id}:{int(now)}"
        try:
            self.store.archive_event(
                "claude_code", external_id, "claude_code",
                short, f"Claude Code {event}", str(payload)[:500],
                project=project,
            )
        except Exception as e:
            logger.error("CC archive failed: %s", e)

        tag = PRIORITY_TAG.get(event, "default")
        logger.info("CC: enqueue (%s) %s", tag, short)
        self.tts_worker.enqueue(short, tag=tag)

    def _handle_stop(self, project: str, session_id: str,
                     transcript_path: str | None = None) -> str | None:
        """Announce Stop; filter by duration; optionally summarize transcript."""
        with self._lock:
            start = self._session_start.pop(session_id, None)
        duration = None
        if start is not None:
            duration = time.time() - start
            if duration < self.stop_min_duration:
                return None

        # Try LLM summary for long-enough sessions with transcript available
        if (self.transcript_summarizer is not None
                and transcript_path
                and (duration is None or duration >= self.summary_min_duration)):
            try:
                summary = self.transcript_summarizer.summarize(
                    transcript_path, project, session_id=session_id)
                if summary:
                    prefix = t(self.language, "cc_summary_prefix", project=project)
                    return prefix + summary
            except Exception as e:
                logger.warning("CC transcript summary failed: %s", e)

        if duration is not None and duration > 300:
            return t(self.language, "cc_long_done", project=project)
        return t(self.language, "cc_stop", project=project)
