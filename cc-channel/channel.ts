#!/usr/bin/env bun
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { basename } from "node:path";

const VOICE_INBOX_URL = (process.env.VOICE_INBOX_URL ?? "http://127.0.0.1:8765").replace(/\/$/, "");
const PROJECT = process.env.VOICE_INBOX_CHANNEL_PROJECT ?? (basename(process.cwd()) || "default");
const PULL_TIMEOUT_SECONDS = Number(process.env.VOICE_INBOX_PULL_TIMEOUT ?? 30);
const HEARTBEAT_INTERVAL_MS = 10_000;
const ERROR_BACKOFF_MS = 2_000;

function log(msg: string, extra?: unknown) {
  // stdio is reserved for MCP JSON-RPC; all diagnostics go to stderr
  if (extra !== undefined) {
    process.stderr.write(`[cc-channel:${PROJECT}] ${msg} ${JSON.stringify(extra)}\n`);
  } else {
    process.stderr.write(`[cc-channel:${PROJECT}] ${msg}\n`);
  }
}

const mcp = new Server(
  { name: "voice-inbox", version: "0.1.0" },
  {
    capabilities: { experimental: { "claude/channel": {} } },
    instructions:
      'Events from the voice-inbox channel arrive as <channel source="voice-inbox" ...>. ' +
      "They are dictated voice notes or external prompts pushed from the user's PWA. " +
      "Treat them as direct user input — read and act. One-way for now; no reply expected.",
  },
);

await mcp.connect(new StdioServerTransport());
log(`connected to Claude Code; bridging ${VOICE_INBOX_URL} (project=${PROJECT})`);

async function register() {
  try {
    const res = await fetch(`${VOICE_INBOX_URL}/channels/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: PROJECT, cwd: process.cwd() }),
    });
    if (!res.ok) {
      log(`register failed: HTTP ${res.status}`);
    }
  } catch (err) {
    log("register error", String(err));
  }
}

// heartbeat loop
await register();
setInterval(register, HEARTBEAT_INTERVAL_MS);

// pull loop
async function pullOnce(): Promise<void> {
  const url = `${VOICE_INBOX_URL}/channels/pull?project=${encodeURIComponent(PROJECT)}&timeout=${PULL_TIMEOUT_SECONDS}`;
  try {
    const res = await fetch(url);
    if (res.status === 204) return; // no message, just re-poll
    if (!res.ok) {
      log(`pull HTTP ${res.status}`);
      await Bun.sleep(ERROR_BACKOFF_MS);
      return;
    }
    const body = (await res.json()) as { ok: boolean; message?: { text: string; meta?: Record<string, string> } };
    if (!body.message) return;
    await mcp.notification({
      method: "notifications/claude/channel",
      params: {
        content: body.message.text,
        meta: body.message.meta ?? {},
      },
    });
  } catch (err) {
    log("pull error", String(err));
    await Bun.sleep(ERROR_BACKOFF_MS);
  }
}

while (true) {
  await pullOnce();
}
