"""
Odczytuje transcript_path z hook payloadu CC i za pomocą LLM robi
1-zdaniowe podsumowanie tego, co agent zrobił w sesji. Używane przez
CCHandler gdy Stop fires i CCConfig.summary_enabled=true.

Żeby nie paść przy dużych sesjach, bierzemy pierwsze N userpromptów i
ostatnie M par (user prompt + tool mix + assistant text), łącznie
tniemy kontekst do ~4k znaków.
"""
import json
import logging
from collections import Counter
from pathlib import Path

from ..i18n import t

logger = logging.getLogger(__name__)


def _extract_turns(transcript_path: str, max_user_prompts: int = 12,
                   max_tool_uses: int = 60) -> dict:
    """
    Parse JSONL transcript. Returns dict with:
      first_prompt, last_prompt, all_prompts (list), tool_mix (Counter),
      last_assistant_text (truncated).
    """
    path = Path(transcript_path)
    if not path.is_file():
        logger.warning("transcript not found: %s", transcript_path)
        return {}

    prompts = []
    tool_uses: list[str] = []
    last_assistant_text = ""

    try:
        with path.open() as f:
            for line in f:
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                msg = obj.get("message")
                if not isinstance(msg, dict):
                    continue
                role = msg.get("role")
                content = msg.get("content")
                if role == "user":
                    if isinstance(content, str):
                        prompts.append(content)
                    elif isinstance(content, list):
                        for c in content:
                            if isinstance(c, dict) and c.get("type") == "text":
                                prompts.append(c.get("text") or "")
                elif role == "assistant" and isinstance(content, list):
                    for c in content:
                        if not isinstance(c, dict):
                            continue
                        ctype = c.get("type")
                        if ctype == "tool_use":
                            tool_uses.append(c.get("name") or "?")
                        elif ctype == "text":
                            last_assistant_text = c.get("text") or last_assistant_text
    except Exception as e:
        logger.warning("transcript parse failed %s: %s", path, e)
        return {}

    # Filter out system-reminder and tool-result user messages which Claude Code
    # injects as 'user' role but aren't actual user input
    real_prompts = [p for p in prompts
                    if p and not p.startswith("<system-")
                    and "<system-reminder>" not in p[:100]]

    return {
        "first_prompt": real_prompts[0] if real_prompts else None,
        "last_prompt": real_prompts[-1] if real_prompts else None,
        "all_prompts": real_prompts[-max_user_prompts:],
        "tool_mix": Counter(tool_uses[-max_tool_uses:]),
        "last_assistant_text": (last_assistant_text or "")[:600],
        "total_tool_uses": len(tool_uses),
    }


def _format_context(turns: dict, project: str) -> str:
    if not turns:
        return ""
    lines = [f"Projekt: {project}"]
    prompts = turns.get("all_prompts") or []
    if prompts:
        lines.append("Prompty użytkownika (chronologicznie):")
        for i, p in enumerate(prompts, 1):
            one = " ".join(p.split())[:220]
            lines.append(f"  {i}. {one}")
    tm = turns.get("tool_mix") or {}
    if tm:
        mix = ", ".join(f"{n} {c}" for n, c in tm.most_common(6))
        lines.append(f"Narzędzia ({turns.get('total_tool_uses', 0)} wywołań): {mix}")
    tail = turns.get("last_assistant_text")
    if tail:
        lines.append("Ostatnia wypowiedź agenta:")
        lines.append("  " + " ".join(tail.split())[:400])
    return "\n".join(lines)


class TranscriptSummarizer:
    def __init__(self, llm, language: str = "pl", max_tokens: int = 120):
        self.llm = llm
        self.language = language
        self.max_tokens = max_tokens
        self._cache: dict[str, str] = {}  # session_id → summary

    def summarize(self, transcript_path: str, project: str,
                  session_id: str | None = None) -> str | None:
        if session_id and session_id in self._cache:
            return self._cache[session_id]

        turns = _extract_turns(transcript_path)
        if not turns or not turns.get("last_prompt"):
            return None

        context = _format_context(turns, project)
        if len(context) < 40:
            return None

        system = t(self.language, "cc_summary_system")
        try:
            text = self.llm.chat(system, context, max_tokens=self.max_tokens).strip()
        except Exception as e:
            logger.warning("CC summary LLM failed: %s", e)
            return None

        if not text or text.upper().startswith("SKIP"):
            return None
        # Drop surrounding quotes if LLM adds them
        if text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        if session_id:
            self._cache[session_id] = text
        return text
