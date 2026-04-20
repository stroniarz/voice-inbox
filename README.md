# Voice Inbox

Lokalny audio-agent na Maca — czyta Ci głosem taski z Linear/Slack/Claude Code + **dwukierunkowa integracja z żywymi sesjami Claude Code** (mów do CC z telefonu, słuchaj odpowiedzi, akceptuj permission dialogi głosem). Streszczanie LLM, digest, priority-based intonacja, push-to-talk PWA.

## Co robi

- **Live notifications** — krótkie powiadomienia ("Linear, nowe zadanie: ..."), zero kosztu LLM
- **Digest co godzinę** — Claude Haiku streszcza eventy z ostatniej godziny do max 6 punktów
- **Priority routing** — Urgent/High dostają ekspresyjniejszy ton (ten sam głos, inne voice_settings)
- **Bi-directional `/channels`** *(nowe)* — dyktuj promty do żywej sesji CC z PWA, Claude odpowiada głosem (`speak` tool), głosowa akceptacja permission dialogów ("tak tak tak" / "nie nie nie")
- **Multi-session aware** — obsługuje N równoległych sesji CC (różne projekty, każdy ma własny target w PWA)
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

## Source: Claude Code (push-based)

Voice Inbox czyta głosem eventy z każdej sesji Claude Code w dowolnym projekcie — bez polling, bez per-repo konfiguracji. Globalny hook w `~/.claude/settings.json` POSTuje każdy event do lokalnego serwera voice-inbox.

**Setup:**

1. Włącz w `config.yaml`:

    ```yaml
    server:
      enabled: true
      port: 8765
    claude_code:
      enabled: true
      stop_min_duration_seconds: 30  # krótsze sesje Stop są ignorowane
      cooldown_seconds: 60           # minimum między ogłoszeniami tego samego typu
    ```

2. Zainstaluj hooki globalnie (raz):

    ```bash
    python3 tools/install_cc_hooks.py
    # lub: python3 tools/install_cc_hooks.py --port 8765
    ```

3. Uruchom voice-inbox jak zwykle. Teraz każda sesja CC (w dowolnym repo) emituje:
   - **Stop** → "Claude Code, sesja w {projekt} zakończona" (jeśli trwała >30s)
   - **SubagentStop** → "Claude Code, subagent w {projekt} zakończony"
   - **Notification** → "Claude Code w {projekt}: {message}" (`critical` tag, ekspresyjniejszy ton — bo oznacza że agent czeka na Ciebie)

**Odinstalowanie:**

```bash
python3 tools/install_cc_hooks.py --remove
```

Tworzy `.bak` na wszelki wypadek.

**Opcjonalnie: session summary (`summary_enabled: true`)** — przy Stop event voice-inbox czyta `transcript_path` z hooka, wyciąga prompty + tool mix + ostatnią wypowiedź agenta i robi 1-zdaniowe LLM podsumowanie:

- Bez summary: "Claude Code, sesja w ircsklep zakończona"
- Z summary: "Claude w ircsklep: dodał autentykację JWT i zrefaktorował middleware"

Cache per session_id — nie podsumowuje tej samej sesji dwa razy. Kosztuje ~$0.001-0.005 za długą sesję na Claude Haiku (darmowo na Ollama).

## Claude Code `/channels` — dwukierunkowa integracja z żywą sesją

Oprócz pasywnych hooków CC (Stop / Notification), voice-inbox wystawia pełną dwukierunkową integrację z feature [`/channels`](https://code.claude.com/docs/en/channels) (research preview, CC v2.1.80+). W praktyce:

- **Dyktuj głosem z PWA** → trafia jako prompt do **konkretnej** żywej sesji CC (wybór projektu z dropdown z 🟢 live indicator)
- **Claude odpowiada głosem** — w sesji CC działa MCP tool `speak`; Claude wołany o krótką rzecz zawoła `speak("zrobione, zmieniłem 3 pliki")` → usłyszysz to z kolumn
- **Głosowa akceptacja permission promptów** — gdy CC pyta o zgodę na Bash/Write/Edit, PWA wyskakuje z bannerem + przyciskami **Tak/Nie**, ewentualnie mówisz *"tak tak tak"* / *"nie nie nie"* i werdykt wraca do CC

### Architektura

```
[PWA mic] ─→ /channels/voice ─→ STT ─→ /channels/push ─→ queue per project
                                 │                              ↑ long-poll
                                 ├→ "tak tak tak" → /channels/permissions/respond
                                 └→ "nie nie nie" → /channels/permissions/respond
                                                                ↓
                          [cc-channel/ Bun MCP subprocess] ─ stdio ─→ [CC session]
                                                ↑
                          /channels/reply ←─────┴─── speak() tool call
                                 │
                                 ↓
                          [voice-inbox TTS worker] → 🔊
```

Jedna instancja voice-inbox obsługuje N sesji CC — każda ma własny `cc-channel/channel.ts` subprocess (spawnowany przez CC przy starcie), długopollujący per-project queue.

### Setup

**1. Zbuduj Bun MCP server** (`cc-channel/`):

```bash
cd cc-channel
bun install
```

**2. Zarejestruj voice-inbox jako MCP server** w `~/.claude.json` (user-level → działa dla każdego projektu):

```json
{
  "mcpServers": {
    "voice-inbox": {
      "command": "bun",
      "args": ["/ABSOLUTE/PATH/TO/voice-inbox/cc-channel/channel.ts"],
      "env": { "VOICE_INBOX_URL": "http://127.0.0.1:8765" }
    }
  }
}
```

Port w `env` musi zgadzać się z `server.port` w `config.yaml`.

**3. Odpal voice-inbox**:

```bash
python3 -m voice_inbox.main --config config.yaml
```

**4. Odpal CC z flagą channels** (w dowolnym projekcie):

```bash
claude --dangerously-load-development-channels server:voice-inbox
```

Flaga `--dangerously-load-development-channels` wymagana podczas research preview (custom channels nie są jeszcze na oficjalnej allowlist Anthropic). Channel server zarejestruje się w voice-inbox pod nazwą `basename(cwd)` (np. `ozebud`).

### Config

```yaml
channels:
  archive_replies: true       # log speak() w DB → widoczne w /status
  archive_permissions: true   # log permission requests + responses (dla obserwacji response latency)
  permissions_language: pl    # pl | en — język TTS announce permission promptów
```

### Endpointy

| Endpoint | Kierunek | Użycie |
|---|---|---|
| `POST /channels/register` | channel → voice-inbox | heartbeat + registry (co 10s) |
| `POST /channels/push {project, text, meta?}` | PWA/curl → voice-inbox | push prompt do CC sesji |
| `GET /channels/pull?project=X&timeout=30` | channel ← voice-inbox | long-poll messages |
| `GET /channels/active` | PWA → voice-inbox | live CC sessions (dropdown) |
| `POST /channels/reply {project, text}` | channel → voice-inbox | CC `speak()` tool |
| `POST /channels/permissions/request` | channel → voice-inbox | permission_request forward |
| `GET /channels/permissions/pending[?project]` | PWA → voice-inbox | banner danych |
| `POST /channels/permissions/respond {project, behavior, request_id?}` | PWA/curl → voice-inbox | resolve permission |
| `GET /channels/permissions/poll?project=X&timeout=30` | channel ← voice-inbox | verdict long-poll |
| `GET /channels/permissions/log?limit=100` | debug | resolved history z latency |
| `POST /channels/voice` | PWA → voice-inbox | multipart audio → STT → routing (push/allow/deny) |

### PWA — co się zmienia

Po włączeniu channels, PWA (`/`) dostaje:
- Dropdown targetów z 🟢 live sessions
- Pomarańczowy banner permission (Tak/Nie buttons + hint głosowy)
- PTT routing: jeśli wybrana żywa sesja → `/channels/voice`; else fallback `/voice` (ask-bot)
- Meta-linijki pod turn: `→ ozebud`, `✓ allow Bash`

### Ograniczenia

- Wymaga **claude.ai login** (research preview); `ANTHROPIC_API_KEY` nie wspiera `/channels`
- Bun wymagany (Node/Deno teoretycznie też zadziałają — MCP SDK JS-only)
- Podczas research preview flaga `--dangerously-load-development-channels` wymagana — po wejściu na oficjalną allowlist Anthropic przejdziesz na `--channels plugin:voice-inbox@...`

## Ask endpoint (rozmowa, nie raport)

Jeśli włączysz `ask.enabled: true` (wymaga `server.enabled: true`), dostajesz dwa dodatkowe endpointy HTTP:

**`POST /ask`** — pytanie tekstem, odpowiedź LLM z kontekstu ostatnich eventów:

```bash
curl -s http://127.0.0.1:8765/ask \
  -H 'content-type: application/json' \
  -d '{"q": "co słychać w ircsklep?"}' | jq
# {"ok":true,"answer":"Claude skończył dwa taski w ircsklep, nowa nitka komentarzy na STR-165. Nic pilnego.","question":"...","project":null}
```

Opcjonalnie `"project": "STR"` filtruje kontekst do jednego projektu (Linear team key / Slack channel / CC repo basename).

**`GET /status?hours=24`** — JSON snapshot: projekty + ostatnie eventy (do debugowania, integracji, UI).

Prompt systemowy (PL/EN w `i18n.py`) wymusza conversational styl: 2-4 zdania, bez list, bez markdownu, gotowe pod TTS.

## Voice mode (push-to-talk PWA)

Włącz `voice.enabled: true` (wymaga `server.enabled` + `ask.enabled`). Dostajesz:

- **PWA pod `/`** — push-to-talk, spacja na Macu / przytrzymanie przycisku na mobile. Ciemny motyw, ikona, manifest, działa jako zainstalowana aplikacja po "Dodaj do ekranu głównego".
- **`POST /voice`** — multipart upload audio → STT (faster-whisper lokalnie albo OpenAI API) → AskHandler → TTS (Twój skonfigurowany provider) → JSON z `transcript`, `answer`, `audio_b64`, `mime`.

**iOS Safari:** mikrofon wymaga HTTPS. Najprościej przez Tailscale Serve:

```bash
tailscale serve --bg --https=443 http://localhost:8765
# otwórz https://twoj-mac.xxx.ts.net na iPhonie → "Udostępnij" → "Do ekranu głównego"
```

**Modele STT (`voice.stt`):**

| provider | model | koszt | uwagi |
|----------|-------|-------|-------|
| `whisper_local` | `tiny` | 0 | szybki, ~75MB, słabszy dla języków |
| `whisper_local` | `small` (default) | 0 | dobry kompromis, ~500MB |
| `whisper_local` | `medium` | 0 | lepszy, ~1.5GB, wolniejszy na CPU |
| `whisper_local` | `large-v3` | 0 | najlepszy, ~3GB, potrzebuje GPU/MPS |
| `openai` | `whisper-1` | $0.006/min | zero setupu, wymaga `OPENAI_API_KEY` |

Model ładuje się lazy (pierwsze nagranie loaduje, potem w pamięci). Faster-whisper używa VAD (`min_silence_duration_ms: 500`) — przytrzymanie PTT z ciszą na końcu nie daje pustego transkryptu.

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
├── adapters/                 # per-source polling (Linear, Slack)
├── cc/                       # Claude Code push handler (via HTTP hooks)
├── llm/                      # LLMClient protocol + adapters (anthropic, openai_compat)
├── tts/                      # TTS adapters (say, elevenlabs, openai) + worker queue
├── stt/                      # STT adapters (whisper_local, openai)
├── ask.py                    # AskHandler — LLM z kontekstu ostatnich eventów
├── server.py                 # FastAPI HTTP server (wszystkie endpointy)
├── channels_bridge.py        # per-project queue dla /channels push/pull
├── channels_permissions.py   # permission broker (pending + verdicts + history)
├── i18n.py                   # PL/EN templates + digest/ask prompts
├── dedup.py                  # SQLite archiwum (events z kolumną project)
├── summarize.py              # Digest generator
├── config.py
└── main.py                   # orchestrator + digest worker
public/                       # PWA (push-to-talk UI, target picker, permission banner)
cc-channel/                   # Bun MCP stdio server dla CC /channels integration
├── channel.ts                # stdio MCP server + speak tool + permission handler
├── package.json              # @modelcontextprotocol/sdk + zod
└── README.md                 # per-module docs
tools/
└── install_cc_hooks.py       # instalator hooków CC w ~/.claude/settings.json
```

## Rozszerzanie

**Nowy adapter** (np. Gmail):

1. `voice_inbox/adapters/gmail.py` z metodą `poll() -> Iterable[Event]`
2. Rejestracja w `main.py::ADAPTERS`
3. Sekcja w `config.yaml::sources`

**Nowy LLM provider**: plik w `voice_inbox/llm/`, dopięcie w `llm/__init__.py::make_llm()`.

**Nowy TTS provider**: analogicznie w `voice_inbox/tts/`.

## Tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest
```

**102 testy** pokrywające: DedupStore (migracja + query), AskHandler (context building), CCHandler (routing + cooldown + summary integration), TranscriptSummarizer (parsing + cache + SKIP), HTTP server (legacy endpoints + static mount), config loading, SayTTS synthesize, ChannelsBridge (per-project queues, register/active TTL, push/pull), PermissionsBroker (pending dict, verdicts queue, respond-by-oldest, history), verdict keyword regex (`tak tak tak` / `nie nie nie` / `yes yes yes` / `no no no`), `/channels/voice` STT-routing.

## Status

Wszystkie podstawowe funkcje działają w produkcji:

- ✅ Linear / Slack adaptery (Linear tested, Slack kod gotowy)
- ✅ Claude Code hooks (Stop / Notification / SubagentStop)
- ✅ Ask + Voice PWA (STT + LLM + TTS pętla)
- ✅ **CC `/channels` bi-directional** — push prompts, `speak` reply tool, permission relay z voice verdicts

W planach:

- Session attention UX — PWA surfacuje **wszystkie** momenty gdy CC czeka na odpowiedź (nie tylko permission), z audio alertem
- Gmail adapter
- SMS / iMessage (odczyt z `~/Library/Messages/chat.db`)
- `/plugin` packaging + submit do official Anthropic marketplace (koniec flagi `--dangerously-load-development-channels`)
- `claude -p` + Codex jako LLM provider (użyj plan quota zamiast API credits)
- Persona system + cached audio clips per-project
- Menubar toggle on/off (SwiftBar)
- Grupowanie eventów na tym samym issue w oknie czasowym (dedup post-hoc)
- Voice cloning własnego głosu przez ElevenLabs

## License

Apache 2.0 (planowana — do dodania).
