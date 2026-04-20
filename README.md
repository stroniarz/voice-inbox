# Voice Inbox

> 🇵🇱 Polska wersja: [README.pl.md](README.pl.md)

Local audio agent for macOS — reads Linear / Slack / Claude Code events to you out loud **and** adds **bi-directional integration with live Claude Code sessions** (dictate prompts to CC from your phone, hear Claude's replies, approve permission dialogs by voice). LLM summarisation, hourly digests, priority-based intonation, push-to-talk PWA.

## What it does

- **Live notifications** — short audio alerts ("Linear, new issue: ..."), zero LLM cost
- **Hourly digest** — Claude Haiku summarises the last hour into max 6 bullet points
- **Priority routing** — Urgent/High issues get an expressive voice profile (same voice, different `voice_settings`)
- **Bi-directional `/channels`** *(new)* — push prompts to a live CC session from the PWA, Claude talks back via the `speak` tool, voice-based approval of permission dialogs ("tak tak tak" / "nie nie nie")
- **Multi-session aware** — handles N parallel CC sessions (different projects, each with its own PWA target)
- **i18n** — PL / EN, all templates and prompts in `i18n.py`
- **Provider-agnostic** — LLM: Anthropic / OpenAI / OpenRouter / DeepSeek / Ollama; TTS: macOS `say` / ElevenLabs / OpenAI TTS
- **No vendor lock-in** — swap engines with a single YAML line

## Quick start

```bash
git clone https://github.com/stroniarz/voice-inbox.git
cd voice-inbox
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp config.example.yaml config.yaml

export ANTHROPIC_API_KEY=sk-ant-...
export LINEAR_API_KEY=lin_api_...
# optional:
export ELEVENLABS_API_KEY=...
export SLACK_USER_TOKEN=xoxp-...

python3 -m voice_inbox.main --config config.yaml
```

## Config

Minimum (free setup with macOS `say`):

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

Full setup with ElevenLabs + priority routing:

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
    voice_id: EXAVITQu4vr4xnSDxMaL   # same voice, different profile
    model: eleven_multilingual_v2
    stability: 0.3                    # more expressive
    speed: 1.2
    api_key_env: ELEVENLABS_API_KEY
```

## LLM providers

```yaml
# Anthropic native
llm: {provider: anthropic, model: claude-haiku-4-5-20251001, api_key_env: ANTHROPIC_API_KEY}

# OpenRouter (one key, many models)
llm: {provider: openrouter, model: anthropic/claude-haiku-4.5, api_key_env: OPENROUTER_API_KEY}

# DeepSeek
llm: {provider: deepseek, model: deepseek-chat, api_key_env: DEEPSEEK_API_KEY}

# Local Gemma via Ollama — zero cost
llm: {provider: ollama, model: gemma3:27b}
```

## Source: Linear

- Personal API key: https://linear.app/settings/account/security
- Polling: `updatedAt > cursor` on issues and comments
- Priority (1 Urgent / 2 High / 3 Normal / 4 Low) routes voice profile

## Source: Slack

User token (`xoxp-...`) with: `im:history, im:read, users:read, search:read, channels:history, groups:history, mpim:history`. Monitors DMs + @mentions.

## Source: Claude Code (push-based hooks)

Voice Inbox reads events from every Claude Code session in any project — no polling, no per-repo config. A global hook in `~/.claude/settings.json` POSTs each event to the local voice-inbox server.

**Setup:**

1. Enable in `config.yaml`:

    ```yaml
    server:
      enabled: true
      port: 8765
    claude_code:
      enabled: true
      stop_min_duration_seconds: 30  # shorter Stop events are ignored
      cooldown_seconds: 60           # minimum gap between same-type announcements
    ```

2. Install the hooks globally (once):

    ```bash
    python3 tools/install_cc_hooks.py
    # or: python3 tools/install_cc_hooks.py --port 8765
    ```

3. Run voice-inbox as usual. Every CC session (in any repo) now emits:
   - **Stop** → "Claude Code, session in {project} finished" (if it lasted >30s)
   - **SubagentStop** → "Claude Code, subagent in {project} finished"
   - **Notification** → "Claude Code in {project}: {message}" (`critical` tag, more expressive tone — this means the agent is waiting on you)

**Uninstall:**

```bash
python3 tools/install_cc_hooks.py --remove
```

Leaves a `.bak` just in case.

**Optional: session summary (`summary_enabled: true`)** — on Stop, voice-inbox reads the `transcript_path` from the hook, extracts prompts + tool mix + the agent's last message and generates a one-sentence LLM summary:

- Without summary: "Claude Code, session in ircsklep finished"
- With summary: "Claude in ircsklep: added JWT auth and refactored middleware"

Cached per session_id — never summarises the same session twice. Costs ~$0.001–0.005 per long session on Claude Haiku (free on Ollama).

## Claude Code `/channels` — bi-directional integration with live sessions

On top of the passive CC hooks (Stop / Notification), voice-inbox exposes a full bi-directional integration with the [`/channels`](https://code.claude.com/docs/en/channels) feature (research preview, CC v2.1.80+). In practice:

- **Dictate by voice from the PWA** → lands as a prompt in a **specific** live CC session (pick target from dropdown with 🟢 live indicator)
- **Claude replies by voice** — the CC session has an MCP tool `speak`; when prompted for a short answer, Claude calls `speak("done, edited 3 files")` → you hear it through the speakers
- **Voice approval of permission prompts** — when CC asks for permission to run Bash/Write/Edit, the PWA pops up a banner with **Yes/No** buttons, or you can say *"tak tak tak"* / *"nie nie nie"* and the verdict flows back to CC (Polish keywords out of the box; English variants `yes yes yes` / `no no no` work too)

### Architecture

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

One voice-inbox instance serves N CC sessions — each gets its own `cc-channel/channel.ts` subprocess (spawned by CC at startup), long-polling a per-project queue.

### Setup

**1. Build the Bun MCP server** (`cc-channel/`):

```bash
cd cc-channel
bun install
```

**2. Register voice-inbox as an MCP server** in `~/.claude.json` (user-level → applies to every project):

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

The port in `env` must match `server.port` in `config.yaml`.

**3. Start voice-inbox:**

```bash
python3 -m voice_inbox.main --config config.yaml
```

**4. Start CC with the channels flag** (in any project):

```bash
claude --dangerously-load-development-channels server:voice-inbox
```

`--dangerously-load-development-channels` is required during the research preview (custom channels aren't on Anthropic's official allowlist yet). The channel server registers with voice-inbox under the name `basename(cwd)` (e.g. `ozebud`).

**Shortcut (optional)** — to avoid pasting the long flag every time, add this function to `~/.zshrc`:

```zsh
# Voice Inbox — Claude Code with /channels auto-enabled
claudev() {
  claude --dangerously-load-development-channels server:voice-inbox "$@"
}
```

After `source ~/.zshrc`:

```bash
cd ~/Projects/my-project
claudev              # CC + voice-inbox channel, immediately
claudev --resume     # resume a session, still with channel
```

Plain `claude` still works without the wrapper — `claudev` is opt-in, it doesn't shadow anything.

### Config

```yaml
channels:
  archive_replies: true       # log each speak() into DB → visible in /status
  archive_permissions: true   # log permission requests + responses (for observing response latency)
  permissions_language: pl    # pl | en — TTS announce language for permission prompts
```

### Endpoints

| Endpoint | Direction | Use |
|---|---|---|
| `POST /channels/register` | channel → voice-inbox | heartbeat + registry (every 10s) |
| `POST /channels/push {project, text, meta?}` | PWA/curl → voice-inbox | push prompt into CC session |
| `GET /channels/pull?project=X&timeout=30` | channel ← voice-inbox | long-poll messages |
| `GET /channels/active` | PWA → voice-inbox | list live CC sessions (dropdown) |
| `POST /channels/reply {project, text}` | channel → voice-inbox | CC's `speak()` tool |
| `POST /channels/permissions/request` | channel → voice-inbox | forward permission_request |
| `GET /channels/permissions/pending[?project]` | PWA → voice-inbox | data for banner |
| `POST /channels/permissions/respond {project, behavior, request_id?}` | PWA/curl → voice-inbox | resolve a permission |
| `GET /channels/permissions/poll?project=X&timeout=30` | channel ← voice-inbox | verdict long-poll |
| `GET /channels/permissions/log?limit=100` | debug | resolved history with latency |
| `POST /channels/voice` | PWA → voice-inbox | multipart audio → STT → routing (push/allow/deny) |

### PWA — what changes

When channels are enabled, the PWA (`/`) gets:
- Target dropdown with 🟢 live sessions
- Orange permission banner (Yes/No buttons + voice hint)
- PTT routing: live session selected → `/channels/voice`; otherwise fallback to `/voice` (ask-bot)
- Meta lines under each turn: `→ ozebud`, `✓ allow Bash`

### Limitations

- Requires **claude.ai login** (research preview); `ANTHROPIC_API_KEY` doesn't support `/channels`
- Bun required (Node/Deno should also work — MCP SDK is JS-only)
- During the research preview the `--dangerously-load-development-channels` flag is required — once the plugin is accepted into Anthropic's official allowlist you switch to `--channels plugin:voice-inbox@...`

## Ask endpoint (conversation, not report)

With `ask.enabled: true` (requires `server.enabled: true`) you get two extra HTTP endpoints:

**`POST /ask`** — text question, LLM answer using recent events as context:

```bash
curl -s http://127.0.0.1:8765/ask \
  -H 'content-type: application/json' \
  -d '{"q": "what is happening in ircsklep?"}' | jq
# {"ok":true,"answer":"Claude finished two tasks in ircsklep, new thread on STR-165. Nothing urgent.","question":"...","project":null}
```

Optional `"project": "STR"` filters context to a single project (Linear team key / Slack channel / CC repo basename).

**`GET /status?hours=24`** — JSON snapshot: projects + recent events (for debugging, integrations, UI).

The system prompt (PL/EN in `i18n.py`) forces a conversational style: 2–4 sentences, no lists, no markdown, ready for TTS.

## Voice mode (push-to-talk PWA)

Enable `voice.enabled: true` (requires `server.enabled` + `ask.enabled`). You get:

- **PWA at `/`** — push-to-talk, space bar on Mac / button hold on mobile. Dark theme, icon, manifest, works as an installed app after "Add to home screen".
- **`POST /voice`** — multipart audio upload → STT (faster-whisper locally or OpenAI API) → AskHandler → TTS (your configured provider) → JSON with `transcript`, `answer`, `audio_b64`, `mime`.

**iOS Safari:** the mic requires HTTPS. The easiest path is Tailscale Serve:

```bash
tailscale serve --bg --https=443 http://localhost:8765
# open https://your-mac.xxx.ts.net on iPhone → "Share" → "Add to home screen"
```

**STT models (`voice.stt`):**

| provider | model | cost | notes |
|----------|-------|------|-------|
| `whisper_local` | `tiny` | 0 | fast, ~75MB, weaker on non-English |
| `whisper_local` | `small` (default) | 0 | good balance, ~500MB |
| `whisper_local` | `medium` | 0 | better, ~1.5GB, slower on CPU |
| `whisper_local` | `large-v3` | 0 | best, ~3GB, needs GPU/MPS |
| `openai` | `whisper-1` | $0.006/min | zero setup, requires `OPENAI_API_KEY` |

Model loads lazily (first recording triggers load, then stays in memory). Faster-whisper uses VAD (`min_silence_duration_ms: 500`) — holding PTT with trailing silence won't give an empty transcript.

## Cost

At 30–50 events/day:

| Component | Cost/month |
|---|---|
| Claude Haiku 4.5 (digest × 24/day) | $1–4 |
| ElevenLabs Creator $22 (100k chars) | $22 |
| ElevenLabs Pro $99 (500k chars) | $99 |
| Total (Creator) | ~$25 |
| macOS `say` | $0 (but sounds synthetic) |

## Structure

```
voice_inbox/
├── adapters/                 # per-source polling (Linear, Slack)
├── cc/                       # Claude Code push handler (via HTTP hooks)
├── llm/                      # LLMClient protocol + adapters (anthropic, openai_compat)
├── tts/                      # TTS adapters (say, elevenlabs, openai) + worker queue
├── stt/                      # STT adapters (whisper_local, openai)
├── ask.py                    # AskHandler — LLM with recent-events context
├── server.py                 # FastAPI HTTP server (all endpoints)
├── channels_bridge.py        # per-project queue for /channels push/pull
├── channels_permissions.py   # permission broker (pending + verdicts + history)
├── i18n.py                   # PL/EN templates + digest/ask prompts
├── dedup.py                  # SQLite archive (events with project column)
├── summarize.py              # Digest generator
├── config.py
└── main.py                   # orchestrator + digest worker
public/                       # PWA (push-to-talk UI, target picker, permission banner)
cc-channel/                   # Bun MCP stdio server for CC /channels integration
├── channel.ts                # stdio MCP server + speak tool + permission handler
├── package.json              # @modelcontextprotocol/sdk + zod
└── README.md                 # per-module docs
tools/
└── install_cc_hooks.py       # CC hooks installer in ~/.claude/settings.json
```

## Extending

**New adapter** (e.g. Gmail):

1. `voice_inbox/adapters/gmail.py` with a `poll() -> Iterable[Event]` method
2. Register in `main.py::ADAPTERS`
3. Add a section in `config.yaml::sources`

**New LLM provider**: file in `voice_inbox/llm/`, wire up in `llm/__init__.py::make_llm()`.

**New TTS provider**: same pattern in `voice_inbox/tts/`.

## Tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest
```

**102 tests** covering: DedupStore (migration + queries), AskHandler (context building), CCHandler (routing + cooldown + summary integration), TranscriptSummarizer (parsing + cache + SKIP), HTTP server (legacy endpoints + static mount), config loading, SayTTS synthesize, ChannelsBridge (per-project queues, register/active TTL, push/pull), PermissionsBroker (pending dict, verdicts queue, respond-by-oldest, history), verdict keyword regex (`tak tak tak` / `nie nie nie` / `yes yes yes` / `no no no`), `/channels/voice` STT routing.

## Status

All core functionality is running in production:

- ✅ Linear / Slack adapters (Linear tested; Slack code ready)
- ✅ Claude Code hooks (Stop / Notification / SubagentStop)
- ✅ Ask + Voice PWA (STT + LLM + TTS loop)
- ✅ **CC `/channels` bi-directional** — push prompts, `speak` reply tool, permission relay with voice verdicts

Planned:

- Session attention UX — PWA surfaces **all** moments when CC is waiting for input (not only permissions), with audio alert
- Gmail adapter
- SMS / iMessage (reads `~/Library/Messages/chat.db`)
- `/plugin` packaging + submit to official Anthropic marketplace (end of the `--dangerously-load-development-channels` flag)
- `claude -p` + Codex as LLM providers (use your CC plan quota instead of API credits)
- Persona system + cached audio clips per project
- Menubar toggle on/off (SwiftBar)
- Grouping events on the same issue within a time window (post-hoc dedup)
- Voice cloning of your own voice via ElevenLabs

## License

Apache 2.0 (planned — to be added).
