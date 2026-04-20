# cc-channel — voice-inbox × Claude Code `/channels` (POC)

Minimal MCP stdio server that pushes HTTP POST bodies into a live Claude Code session via the
[channels](https://code.claude.com/docs/en/channels-reference) contract.

**Phase 1 scope:** one-way push only (no reply tool, no permission relay, no voice-inbox HTTP bridge).
Proof that `--dangerously-load-development-channels` works on this setup before building the real integration.

## Requirements

- Claude Code v2.1.80+ (`claude --version`)
- Bun installed (`bun --version`)
- claude.ai login (not `ANTHROPIC_API_KEY`) — required by channels feature

## Install

```bash
cd cc-channel
bun install
```

## Wire it into a project

Copy `.mcp.json.example` to `.mcp.json` in the project where you want voice-inbox push, and replace
the absolute path to `channel.ts`. Or add the entry to `~/.claude.json` (user-level) for every project.

## Run it

```bash
claude --dangerously-load-development-channels server:voice-inbox
```

During the research preview, custom channels need this flag. After `/plugin` packaging (Phase 6), it
becomes `--channels plugin:voice-inbox@...`.

## Smoke test

From another terminal:

```bash
curl -X POST localhost:8788 -d "list files in this directory"
```

Expected: the CC session receives a `<channel source="voice-inbox" path="/" method="POST">` tag and
Claude reacts to the instruction.

If nothing arrives, check `~/.claude/debug/<session-id>.txt` for stderr from the spawned subprocess.

## Environment

- `VOICE_INBOX_CHANNEL_PORT` — override HTTP listener port (default `8788`)
