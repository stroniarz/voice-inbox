"""
AskHandler — odpowiada na pytania użytkownika używając ostatnich eventów
jako kontekstu. Używane przez /ask endpoint (tekst) oraz /voice (PR 4, audio).
"""
import logging
from datetime import datetime, timezone

from .i18n import t

logger = logging.getLogger(__name__)


class AskHandler:
    def __init__(self, llm, store, language: str = "pl",
                 history_hours: int = 24,
                 max_events: int = 80,
                 max_tokens: int = 400):
        self.llm = llm
        self.store = store
        self.language = language
        self.history_hours = history_hours
        self.max_events = max_events
        self.max_tokens = max_tokens

    def _format_event(self, e: dict) -> str:
        ts = e.get("created_at", "")
        try:
            when = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            delta = datetime.now(timezone.utc) - when
            mins = int(delta.total_seconds() // 60)
            if mins < 60:
                rel = f"{mins}min temu"
            elif mins < 1440:
                rel = f"{mins // 60}h temu"
            else:
                rel = f"{mins // 1440}d temu"
        except Exception:
            rel = ts[:16]
        project = e.get("project") or "?"
        source = e.get("source") or ""
        short = e.get("short") or ""
        title = e.get("title") or ""
        return f"[{rel}] {source}/{project}: {short} ({title})"

    def build_context(self, project: str | None = None) -> str:
        events = self.store.recent_events(
            hours=self.history_hours,
            project=project,
            limit=self.max_events,
        )
        projects = self.store.project_summary(hours=self.history_hours)

        if not events and not projects:
            return t(self.language, "ask_context_empty")

        lines = []
        if projects:
            lines.append(t(self.language, "ask_context_projects_header"))
            for p in projects[:20]:
                lines.append(
                    f"- {p['project']} / {p['source']}: {p['count']} "
                    f"events, ostatni {p['last_at'][:16]}"
                )
            lines.append("")

        if events:
            lines.append(t(self.language, "ask_context_events_header"))
            for e in events[:self.max_events]:
                lines.append(self._format_event(e))

        return "\n".join(lines)

    def ask(self, question: str, project: str | None = None) -> str:
        context = self.build_context(project=project)
        system = t(self.language, "ask_system")
        user_msg = t(self.language, "ask_user_template",
                     context=context, question=question)
        try:
            return self.llm.chat(system, user_msg, max_tokens=self.max_tokens).strip()
        except Exception as e:
            logger.exception("Ask LLM call failed: %s", e)
            return t(self.language, "ask_error")
