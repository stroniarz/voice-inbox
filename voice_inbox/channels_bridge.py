"""Bridge between the voice-inbox HTTP server and one or more CC /channels MCP
subprocesses (see tools/voice-inbox/cc-channel/channel.ts).

Each CC session registers a channel by its project name (typically basename of
the CC process cwd). The PWA or any external caller pushes a message through
`POST /channels/push`, which enqueues on that project's queue. The matching
channel server long-polls `GET /channels/pull` and emits the message as an MCP
notification into its CC session.
"""

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)

HEARTBEAT_TTL_SECONDS = 60  # a project is "active" if registered within this window


class ChannelsBridge:
    def __init__(self, heartbeat_ttl: float = HEARTBEAT_TTL_SECONDS):
        self._queues: dict[str, asyncio.Queue] = {}
        self._last_seen: dict[str, dict[str, Any]] = {}
        self._heartbeat_ttl = heartbeat_ttl
        self._lock = asyncio.Lock()

    async def _get_queue(self, project: str) -> asyncio.Queue:
        async with self._lock:
            q = self._queues.get(project)
            if q is None:
                q = asyncio.Queue(maxsize=256)
                self._queues[project] = q
            return q

    async def register(self, project: str, cwd: str | None = None) -> None:
        await self._get_queue(project)  # ensure queue exists so pull can block on it
        self._last_seen[project] = {"cwd": cwd, "ts": time.time()}
        logger.debug("channels: registered %s (cwd=%s)", project, cwd)

    async def push(self, project: str, text: str, meta: dict[str, str] | None = None) -> bool:
        q = await self._get_queue(project)
        try:
            q.put_nowait({"text": text, "meta": meta or {}})
            return True
        except asyncio.QueueFull:
            logger.warning("channels: queue full for %s, dropping message", project)
            return False

    async def pull(self, project: str, timeout: float) -> dict | None:
        q = await self._get_queue(project)
        try:
            return await asyncio.wait_for(q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def active_projects(self) -> list[dict[str, Any]]:
        now = time.time()
        out = []
        for project, info in self._last_seen.items():
            if now - info["ts"] <= self._heartbeat_ttl:
                out.append({
                    "project": project,
                    "cwd": info.get("cwd"),
                    "last_seen_ago_seconds": round(now - info["ts"], 1),
                })
        return sorted(out, key=lambda x: x["project"])
