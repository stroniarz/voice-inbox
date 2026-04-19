# Voice Inbox

Lokalny audio-notyfikator na Maca — czyta Ci głosem nowe zadania z Linear (+ gotowe pod Slack, w planach Gmail / SMS / Asana). Streszczanie przez LLM, digest co godzinę, priority-based intonacja.

## Co robi

- **Live** — krótkie powiadomienia ("Linear, nowe zadanie: ..."), zero kosztu LLM
- **Digest co godzinę** — Claude Haiku streszcza eventy z ostatniej godziny do max 6 punktów
- **Priority routing** — issues z priority Urgent/High dostają ekspresyjniejszy ton (ten sam głos, inne voice_settings)
- **i18n** — PL / EN w configu, pełne teksty i prompty
- **Provider-agnostic** — LLM: Anthropic / OpenAI / OpenRouter / DeepSeek / Ollama; TTS: macOS `say` / ElevenLabs / OpenAI TTS
- **Zero vendor lock-in** — wymiana silnika to jedna linia w YAML

## Start

```bash
git clone https://github.com/stroniarz/voice-inbox.git
cd voice-inbox
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml

export ANTHROPIC_API_KEY=sk-ant-...
export LINEAR_API_KEY=lin_api_...
# opcjonalnie:
export ELEVENLABS_API_KEY=...
export SLACK_USER_TOKEN=xoxp-...

python3 -m voice_inbox.main --config config.yaml
```

## Config

Minimum (darmowy setup z macOS `say`):

```yaml
language: pl   # pl | en

llm:
  provider: anthropic
  model: claude-haiku-4-5-20251001
  api_key_env: ANTHROPIC_API_KEY

tts:
  provider: say
  voice: Zosia   # PL: Zosia / Krzysztof; EN: Samantha / Ava
  rate: 180

sources:
  linear:
    enabled: true
    api_key_env: LINEAR_API_KEY
```

Pełna wersja z ElevenLabs + priority routing:

```yaml
tts:
  default:
    provider: elevenlabs
    voice_id: EXAVITQu4vr4xnSDxMaL
    model: eleven_multilingual_v2
    stability: 0.5
    speed: 1.2
    api_key_env: ELEVENLABS_API_KEY
  critical:
    provider: elevenlabs
    voice_id: EXAVITQu4vr4xnSDxMaL   # ten sam głos, inny profil
    model: eleven_multilingual_v2
    stability: 0.3                    # bardziej ekspresyjny
    speed: 1.2
    api_key_env: ELEVENLABS_API_KEY
```

## LLM providers

```yaml
# Anthropic native
llm: {provider: anthropic, model: claude-haiku-4-5-20251001, api_key_env: ANTHROPIC_API_KEY}

# OpenRouter (jeden klucz, wszystkie modele)
llm: {provider: openrouter, model: anthropic/claude-haiku-4.5, api_key_env: OPENROUTER_API_KEY}

# DeepSeek
llm: {provider: deepseek, model: deepseek-chat, api_key_env: DEEPSEEK_API_KEY}

# Lokalna Gemma przez Ollama — zero kosztów
llm: {provider: ollama, model: gemma3:27b}
```

## Source: Linear

- Personal API key: https://linear.app/settings/account/security
- Polling: `updatedAt > cursor` na issues i comments
- Priority (1 Urgent / 2 High / 3 Normal / 4 Low) routuje voice profile

## Source: Slack

User token (`xoxp-...`) z: `im:history, im:read, users:read, search:read, channels:history, groups:history, mpim:history`. Monitoruje DMs + @mentions.

## Koszty

Przy 30-50 eventach/dzień:

| Komponent | Koszt/mies |
|---|---|
| Claude Haiku 4.5 (digest × 24/dzień) | 5-15 zł |
| ElevenLabs Creator $22 (100k znaków) | $22 |
| ElevenLabs Pro $99 (500k znaków) | $99 |
| Razem (Creator) | ~$25 |
| macOS `say` | 0 zł (ale brzmi syntetycznie) |

## Struktura

```
voice_inbox/
├── adapters/       # per-source polling (Linear, Slack)
├── llm/            # LLMClient protocol + adapters (anthropic, openai_compat)
├── tts/            # TTSClient protocol + adapters (say, elevenlabs, openai) + worker queue
├── i18n.py         # PL/EN templates + digest prompts
├── dedup.py        # SQLite archiwum + cursors
├── summarize.py    # Digest generator
├── config.py
└── main.py         # orchestrator + digest worker
```

## Rozszerzanie

**Nowy adapter** (np. Gmail):

1. `voice_inbox/adapters/gmail.py` z metodą `poll() -> Iterable[Event]`
2. Rejestracja w `main.py::ADAPTERS`
3. Sekcja w `config.yaml::sources`

**Nowy LLM provider**: plik w `voice_inbox/llm/`, dopięcie w `llm/__init__.py::make_llm()`.

**Nowy TTS provider**: analogicznie w `voice_inbox/tts/`.

## Status

MVP działający na Linear. W planach:

- Slack adapter (kod gotowy, nieprzetestowany — potrzebuje user tokena)
- Gmail adapter
- SMS / iMessage (odczyt z `~/Library/Messages/chat.db`)
- Menubar toggle on/off (SwiftBar)
- Grupowanie eventów na tym samym issue w oknie czasowym (dedup post-hoc)
- Voice cloning własnego głosu przez ElevenLabs

## License

Apache 2.0 (planowana — do dodania).
