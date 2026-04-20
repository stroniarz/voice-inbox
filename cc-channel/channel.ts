#!/usr/bin/env bun
import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

const HTTP_PORT = Number(process.env.VOICE_INBOX_CHANNEL_PORT ?? 8788);

const mcp = new Server(
  { name: "voice-inbox", version: "0.0.1" },
  {
    capabilities: { experimental: { "claude/channel": {} } },
    instructions:
      'Events from the voice-inbox channel arrive as <channel source="voice-inbox" ...>. ' +
      "They are dictated voice notes or external prompts pushed from the user's PWA. " +
      "Treat them as direct user input — read and act. One-way in this POC phase; no reply expected.",
  },
);

await mcp.connect(new StdioServerTransport());

Bun.serve({
  port: HTTP_PORT,
  hostname: "127.0.0.1",
  async fetch(req) {
    if (req.method !== "POST") {
      return new Response("voice-inbox channel: POST body to push into CC session", { status: 405 });
    }
    const body = await req.text();
    const url = new URL(req.url);
    await mcp.notification({
      method: "notifications/claude/channel",
      params: {
        content: body,
        meta: { path: url.pathname, method: req.method },
      },
    });
    return new Response("ok");
  },
});
