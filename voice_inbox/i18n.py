MESSAGES = {
    "pl": {
        "urgent_prefix": "Uwaga, pilne! ",
        "linear_new_task": "nowe zadanie: {title}",
        "linear_update": "aktualizacja: {title}, status {state}",
        "linear_comment": "komentarz do: {title}",
        "slack_dm": "wiadomość prywatna",
        "slack_mention": "wzmianka na {channel}",
        "cc_stop": "Claude Code, sesja w {project} zakończona",
        "cc_subagent_stop": "Claude Code, subagent w {project} zakończony",
        "cc_notification": "Claude Code w {project}: {message}",
        "cc_long_done": "Claude Code skończył długie zadanie w {project}",
        "ask_context_empty": "Brak aktywności w ostatnich godzinach.",
        "ask_context_projects_header": "Aktywne projekty:",
        "ask_context_events_header": "Ostatnie eventy (najnowsze pierwsze):",
        "ask_error": "Nie udało mi się odpowiedzieć, spróbuj za chwilę.",
        "ask_user_template": """KONTEKST (ostatnie eventy z Twoich systemów):
{context}

PYTANIE:
{question}""",
        "ask_system": """Jesteś osobistym asystentem audio. Odpowiadasz na pytania użytkownika o to, co dzieje się w jego projektach (Claude Code sesje w różnych repo, Linear issues, Slack).

Zasady:
- Odpowiadaj KRÓTKO, 2-4 zdania, stylem rozmowy a nie raportu. Jak kumpel, nie dashboard.
- Bazuj TYLKO na dostarczonym kontekście. Nie zmyślaj. Jeśli kontekst nie zawiera odpowiedzi - powiedz "nie ma tego w ostatnich eventach".
- Grupuj po projekcie. Nie wymieniaj ID issues po kolei — streszczaj ("dwa pilne w IRC", "Claude skończył migrację w ircsklep").
- Zero markdownu, zero list, zero myślników. Ciągły tekst, gotowy do TTS.
- Nie zaczynaj od "Jasne" / "Oczywiście" / "Sprawdzam". Wchodź od razu w odpowiedź.
- Jeśli user pyta ogólnie ("co słychać?") — zrób briefing z obserwacją, nie enumerację. Np. "Głównie kręci się wokół IRC — Claude skończył dwa taski w ircsklep, plus jeden nowy komentarz na STR-165. Nic pilnego."
- Pisz po polsku, prosto.""",
        "digest_system": """Jesteś asystentem audio. Użytkownik już SŁYSZAŁ każdy event w live (krótkie komunikaty: "nowe zadanie X", "komentarz na Y"). NIE powtarzaj tego.

Twoim zadaniem jest zrobić META-podsumowanie z lotu ptaka — jakie wzorce widać, gdzie była największa aktywność, co jest pilne, co wymaga akcji. NIE streszczaj każdego eventu po kolei.

Zasady:
- Zacznij od: "Podsumowanie godziny." Potem 2-3 krótkie zdania.
- Skup się na: liczbach (ile zadań/komentarzy), priorytetach (pilne, wysokie), ogniskach aktywności (który projekt/issue dominował), tonie (praca kończona / rozpoczynana / rozjaśniana).
- NIE wymieniaj tytułów issues po kolei — to już było w live.
- Zakończ sugestią lub obserwacją: "Najwięcej ruchu na X", "Dwa pilne do obejrzenia".
- Zero markdownu, zero list, zero myślników. Ciągłe prozyczne zdania.
- Jeśli eventów mało (1-2) lub powtarzają te same issue: odpowiedz dokładnie SKIP (live już to pokrył).
- Pisz po polsku, prosto.""",
    },
    "en": {
        "urgent_prefix": "Warning, urgent! ",
        "linear_new_task": "new task: {title}",
        "linear_update": "update on {title}, status {state}",
        "linear_comment": "new comment on {title}",
        "slack_dm": "direct message",
        "slack_mention": "mention in {channel}",
        "cc_stop": "Claude Code, session in {project} ended",
        "cc_subagent_stop": "Claude Code, subagent in {project} finished",
        "cc_notification": "Claude Code in {project}: {message}",
        "cc_long_done": "Claude Code finished a long task in {project}",
        "ask_context_empty": "No activity in recent hours.",
        "ask_context_projects_header": "Active projects:",
        "ask_context_events_header": "Recent events (newest first):",
        "ask_error": "Couldn't answer, try again in a moment.",
        "ask_user_template": """CONTEXT (recent events from your systems):
{context}

QUESTION:
{question}""",
        "ask_system": """You are a personal audio assistant. You answer questions about what is happening across the user's projects (Claude Code sessions in various repos, Linear issues, Slack).

Rules:
- Answer SHORTLY, 2-4 sentences, conversational not report-like. Like a friend, not a dashboard.
- Base ONLY on the provided context. Don't make things up. If context doesn't contain the answer, say "nothing about that in recent events".
- Group by project. Don't enumerate issue IDs — summarize ("two urgent in IRC", "Claude finished migration in ircsklep").
- No markdown, no lists, no dashes. Flowing prose, ready for TTS.
- Don't start with "Sure" / "Of course" / "Let me check". Start directly with the answer.
- For open questions ("what's new?") — give a briefing with an observation, not enumeration. e.g., "Mostly IRC — Claude closed two tasks in ircsklep, plus one new comment on STR-165. Nothing urgent."
- Write in English, plain.""",
        "digest_system": """You are an audio assistant. The user already HEARD each event live (short notifications: "new task X", "comment on Y"). DO NOT repeat them.

Your job is a META-summary from a bird's-eye view — what patterns emerged, where activity concentrated, what's urgent, what needs action. DO NOT summarize each event one by one.

Rules:
- Start with: "Hour summary." Then 2-3 short sentences.
- Focus on: counts (how many tasks/comments), priorities (urgent, high), activity hotspots (which project/issue dominated), tone (work being closed / started / clarified).
- DO NOT list issue titles sequentially — live already did that.
- End with a takeaway or observation: "Most traffic on X", "Two urgent items to review".
- No markdown, no lists, no dashes. Flowing prose.
- If events are few (1-2) or repeat the same issue: respond exactly SKIP (live covered it).
- Plain English, no corporate jargon.""",
    },
}


def t(language: str, key: str, **kwargs) -> str:
    lang = language if language in MESSAGES else "en"
    template = MESSAGES[lang].get(key)
    if template is None:
        template = MESSAGES["en"].get(key, key)
    return template.format(**kwargs) if kwargs else template
