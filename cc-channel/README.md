# cc-channel — voice-inbox × Claude Code `/channels`

MCP stdio server that bridges voice-inbox to a live Claude Code session via the
[channels](https://code.claude.com/docs/en/channels-reference) contract.

**Phase 2 architecture:**

```
[PWA mic / curl] → voice-inbox :8765 → in-memory queue per project
                                        ↑ long-poll (30s)
                                        └── channel.ts (this subprocess)
                                               ↓ stdio notification
                                            [CC session X]
```

One voice-inbox instance, N channel subprocesses (one per running CC session).
The channel server has no HTTP listener of its own — it pulls from voice-inbox's
`/channels/pull` endpoint keyed by project name (basename of its cwd).

## Requirements

- Claude Code v2.1.80+ (`claude --version`)
- Bun (`bun --version`)
- claude.ai login (not `ANTHROPIC_API_KEY`) — channels requirement
- voice-inbox running on `http://127.0.0.1:8765` (default)

## Install

```bash
cd cc-channel
bun install
```

## Wire it in

Add voice-inbox to your user-level `~/.claude.json` so every project picks it up:

```json
{
  "mcpServers": {
    "voice-inbox": {
      "command": "bun",
      "args": ["/ABSOLUTE/PATH/TO/voice-inbox/cc-channel/channel.ts"]
    }
  }
}
```

Per-project: drop `.mcp.json.example` (rewritten with your absolute path) as `.mcp.json`.

## Run

Start voice-inbox first (separate terminal), then start CC with channels:

```bash
claude --dangerously-load-development-channels server:voice-inbox
```

At startup the channel subprocess registers itself with voice-inbox under the
project name `basename(cwd)` (e.g. `ozebud`) and begins long-polling.

## Smoke test

```bash
curl -X POST http://127.0.0.1:8765/channels/push \
     -H 'Content-Type: application/json' \
     -d '{"project": "ozebud", "text": "list files in this directory"}'
```

Expected: the CC session for project `ozebud` receives
`<channel source="voice-inbox" ...>list files...</channel>` and Claude reacts.

Other useful endpoints:
- `GET /channels/active` — lists active projects (PWA dropdown source)
- `GET /channels/pull?project=X&timeout=30` — what channel.ts polls
- `POST /channels/register` — what channel.ts calls on startup + every 10s

## Environment

- `VOICE_INBOX_URL` — voice-inbox base URL (default `http://127.0.0.1:8765`)
- `VOICE_INBOX_CHANNEL_PROJECT` — override project name (default `basename(cwd)`)
- `VOICE_INBOX_PULL_TIMEOUT` — long-poll timeout seconds (default `30`)

## Troubleshooting

- `/mcp` in CC session shows channel status. "Failed to connect" → check stderr
  in `~/.claude/debug/<session-id>.txt` for Bun errors.
- Channel server logs to stderr (`[cc-channel:project] ...`); stdin/stdout are
  reserved for MCP JSON-RPC.
- If voice-inbox is down when CC starts, the channel server retries on 2s backoff
  and registers as soon as voice-inbox comes up.
