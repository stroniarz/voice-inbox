#!/usr/bin/env bun
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { CallToolRequestSchema, ListToolsRequestSchema } from "@modelcontextprotocol/sdk/types.js";
import { basename } from "node:path";
import { z } from "zod";

const VOICE_INBOX_URL = (process.env.VOICE_INBOX_URL ?? "http://127.0.0.1:8765").replace(/\/$/, "");
const PROJECT = process.env.VOICE_INBOX_CHANNEL_PROJECT ?? (basename(process.cwd()) || "default");
const PULL_TIMEOUT_SECONDS = Number(process.env.VOICE_INBOX_PULL_TIMEOUT ?? 30);
const HEARTBEAT_INTERVAL_MS = 10_000;
const ERROR_BACKOFF_MS = 2_000;

function log(msg: string, extra?: unknown) {
  if (extra !== undefined) {
    process.stderr.write(`[cc-channel:${PROJECT}] ${msg} ${JSON.stringify(extra)}\n`);
  } else {
    process.stderr.write(`[cc-channel:${PROJECT}] ${msg}\n`);
  }
}

const mcp = new Server(
  { name: "voice-inbox", version: "0.3.0" },
  {
    capabilities: {
      experimental: {
        "claude/channel": {},
        "claude/channel/permission": {},  // phase 4: relay tool-use approvals
      },
      tools: {},
    },
    instructions:
      'Events from the voice-inbox channel arrive as <channel source="voice-inbox" ...>. ' +
      "They are voice-dictated notes or prompts pushed from the user's PWA. " +
      "Treat them as direct user input. " +
      "When the reply is short and conversational (1-2 sentences, a confirmation, a summary), call the `speak` tool " +
      "with that text so the user hears it without looking at the terminal. " +
      "Skip `speak` for long outputs, file contents, code, or when the user is clearly at the terminal.",
  },
);

// --- speak tool (phase 3) ----------------------------------------------------
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

// --- permission relay (phase 4) ---------------------------------------------
const PermissionRequestSchema = z.object({
  method: z.literal("notifications/claude/channel/permission_request"),
  params: z.object({
    request_id: z.string(),
    tool_name: z.string(),
    description: z.string(),
    input_preview: z.string(),
  }),
});

mcp.setNotificationHandler(PermissionRequestSchema, async ({ params }) => {
  log("permission request received", { request_id: params.request_id, tool: params.tool_name });
  try {
    const res = await fetch(`${VOICE_INBOX_URL}/channels/permissions/request`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: PROJECT, ...params }),
    });
    if (!res.ok) {
      const detail = await res.text();
      log(`permission forward failed: HTTP ${res.status} ${detail}`);
    }
  } catch (err) {
    log("permission forward error", String(err));
  }
});

await mcp.connect(new StdioServerTransport());
log(`connected; bridging ${VOICE_INBOX_URL} (project=${PROJECT})`);

// --- registration heartbeat -------------------------------------------------
async function register() {
  try {
    const res = await fetch(`${VOICE_INBOX_URL}/channels/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: PROJECT, cwd: process.cwd() }),
    });
    if (!res.ok) log(`register failed: HTTP ${res.status}`);
  } catch (err) {
    log("register error", String(err));
  }
}
await register();
setInterval(register, HEARTBEAT_INTERVAL_MS);

// --- pull loop: inbound channel messages ------------------------------------
async function pullMessages(): Promise<void> {
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
      params: { content: body.message.text, meta: body.message.meta ?? {} },
    });
  } catch (err) {
    log("pull error", String(err));
    await Bun.sleep(ERROR_BACKOFF_MS);
  }
}

// --- pull loop: permission verdicts -----------------------------------------
async function pullVerdicts(): Promise<void> {
  const url = `${VOICE_INBOX_URL}/channels/permissions/poll?project=${encodeURIComponent(PROJECT)}&timeout=${PULL_TIMEOUT_SECONDS}`;
  try {
    const res = await fetch(url);
    if (res.status === 204) return;
    if (!res.ok) {
      log(`verdict poll HTTP ${res.status}`);
      await Bun.sleep(ERROR_BACKOFF_MS);
      return;
    }
    const body = (await res.json()) as { ok: boolean; verdict?: { request_id: string; behavior: "allow" | "deny" } };
    if (!body.verdict) return;
    await mcp.notification({
      method: "notifications/claude/channel/permission",
      params: { request_id: body.verdict.request_id, behavior: body.verdict.behavior },
    });
    log(`verdict delivered`, body.verdict);
  } catch (err) {
    log("verdict poll error", String(err));
    await Bun.sleep(ERROR_BACKOFF_MS);
  }
}

// run both loops concurrently — one per kind
(async () => { while (true) await pullMessages(); })();
(async () => { while (true) await pullVerdicts(); })();
