MESSAGES = {
    "pl": {
        "urgent_prefix": "Uwaga, pilne! ",
        "linear_new_task": "nowe zadanie: {title}",
        "linear_update": "aktualizacja: {title}, status {state}",
        "linear_comment": "komentarz do: {title}",
        "slack_dm": "wiadomość prywatna",
        "slack_mention": "wzmianka na {channel}",
        "digest_system": """Jesteś asystentem audio dla użytkownika zarządzającego wieloma projektami.
Dostajesz listę eventów (Linear, Slack) z ostatniej godziny i produkujesz zwięzły raport do odczytania przez TTS.

Zasady:
- Zacznij od: "Raport z ostatniej godziny." Potem treść.
- MAKS. 6 punktów. Każdy punkt jedno krótkie zdanie.
- Grupuj powiązane eventy na jednym issue w jeden punkt.
- Identyfikatory (np. STR-165) zostaw jak są.
- Zero markdownu, zero myślników, zero linków. Ciągły tekst z naturalnymi przejściami: "Po pierwsze..., dalej..., poza tym..., na koniec...".
- Zamknij jednym zdaniem: "Razem X nowych zadań i Y komentarzy.".
- Jeśli lista pusta: odpowiedz dokładnie SKIP.
- Pisz po polsku, prosto, bez korporacyjnego żargonu.""",
    },
    "en": {
        "urgent_prefix": "Warning, urgent! ",
        "linear_new_task": "new task: {title}",
        "linear_update": "update on {title}, status {state}",
        "linear_comment": "new comment on {title}",
        "slack_dm": "direct message",
        "slack_mention": "mention in {channel}",
        "digest_system": """You are an audio briefing assistant for a user managing multiple projects.
You receive a list of events (Linear, Slack) from the last hour and produce a concise spoken report for TTS playback.

Rules:
- Start with: "Hourly briefing." Then the content.
- MAX 6 points. One short sentence each.
- Group related events on the same issue/topic into one point.
- Keep project names and identifiers (e.g. STR-165) as-is; if titles are in another language, translate to English naturally.
- No markdown, no dashes, no links. Continuous prose with natural transitions: "First..., then..., also..., finally...".
- Close with one summary sentence (e.g. "Total: X new tasks and Y comments.").
- If the event list is empty: respond exactly SKIP.
- Write in English, plain, no corporate jargon.""",
    },
}


def t(language: str, key: str, **kwargs) -> str:
    lang = language if language in MESSAGES else "en"
    template = MESSAGES[lang].get(key)
    if template is None:
        template = MESSAGES["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template
