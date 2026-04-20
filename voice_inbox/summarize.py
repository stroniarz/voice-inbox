from .llm.base import LLMClient
from .i18n import t


class Summarizer:
    def __init__(self, llm: LLMClient, language: str = "pl"):
        self.llm = llm
        self.language = language

    def digest(self, events: list[dict]) -> str | None:
        if not events:
            return None
        lines = []
        for e in events:
            body = (e.get("body") or "").strip()
            if len(body) > 400:
                body = body[:400] + "…"
            project = e.get("project")
            source_tag = f"{e['source']}/{project}" if project else e['source']
            lines.append(
                f"- [{source_tag}] {e['author']} | {e['title']}\n  {body}"
            )
        content = "Eventy:\n\n" + "\n".join(lines)
        system = t(self.language, "digest_system")
        text = self.llm.chat(system=system, user=content, max_tokens=600)
        if text.upper() == "SKIP" or not text:
            return None
        return text
