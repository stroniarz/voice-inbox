#!/usr/bin/env bun
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
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
  { name: "voice-inbox", version: "0.2.0" },
  {
    capabilities: {
      experimental: { "claude/channel": {} },
      tools: {},  // phase 3: expose `speak` so CC can reply through voice-inbox TTS
    },
    instructions:
      'Events from the voice-inbox channel arrive as <channel source="voice-inbox" ...>. ' +
      "They are voice-dictated notes or prompts pushed from the user's PWA. " +
      "Treat them as direct user input. " +
      "When the reply is short and conversational (1-2 sentences, a confirmation, a summary), call the `speak` tool " +
      "with that text so the user hears it without looking at the terminal. " +
      "Skip `speak` for long outputs, file contents, code, or when the user is clearly at the terminal " +
      "(they can read the transcript themselves).",
  },
);

mcp.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: "speak",
      description:
        "Speak a short conversational reply back to the user through voice-inbox TTS. " +
        "Use for 1-2 sentence confirmations, summaries, or acknowledgements when the user is likely away from the terminal. " +
        "Skip this for long outputs, code, or detailed file dumps.",
      inputSchema: {
        type: "object",
        properties: {
          text: {
            type: "string",
            description: "The text to speak aloud. Keep it short and natural — this will be synthesised as audio.",
          },
        },
        required: ["text"],
      },
    },
  ],
}));

mcp.setRequestHandler(CallToolRequestSchema, async (req) => {
  if (req.params.name === "speak") {
    const { text } = (req.params.arguments ?? {}) as { text?: string };
    if (!text || typeof text !== "string") {
      throw new Error("speak: 'text' argument is required and must be a string");
    }
    try {
      const res = await fetch(`${VOICE_INBOX_URL}/channels/reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ project: PROJECT, text }),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(`voice-inbox /channels/reply HTTP ${res.status}: ${detail}`);
      }
    } catch (err) {
      log("speak error", String(err));
      throw err;
    }
    return { content: [{ type: "text", text: "spoken" }] };
  }
  throw new Error(`unknown tool: ${req.params.name}`);
});

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

await register();
setInterval(register, HEARTBEAT_INTERVAL_MS);

async function pullOnce(): Promise<void> {
  const url = `${VOICE_INBOX_URL}/channels/pull?project=${encodeURIComponent(PROJECT)}&timeout=${PULL_TIMEOUT_SECONDS}`;
  try {
    const res = await fetch(url);
    if (res.status === 204) return;
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
