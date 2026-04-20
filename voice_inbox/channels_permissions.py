"""Permission relay broker for CC /channels permission_request notifications.

When CC opens a tool-use approval dialog in a channel'ed session, Claude Code
emits `notifications/claude/channel/permission_request` to the channel MCP
server. channel.ts forwards that to the voice-inbox HTTP broker here; the user
responds (voice / PWA / curl) and the verdict is pulled by channel.ts and sent
back as `notifications/claude/channel/permission` to CC.

The broker keeps two structures per project:
- pending: request_id -> {tool_name, description, input_preview, created_ts}
- verdicts: asyncio.Queue of {request_id, behavior}  — consumed by channel.ts poll
And a flat `history` list of resolved entries for observation (later → informed
TTL decisions).
"""

import asyncio
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class PermissionsBroker:
    def __init__(self):
        self._pending: dict[str, dict[str, dict[str, Any]]] = {}  # project -> request_id -> req
        self._verdicts: dict[str, asyncio.Queue] = {}  # project -> queue of verdict dicts
        self._history: list[dict[str, Any]] = []  # resolved + unresolved, bounded
        self._history_cap = 500
        self._lock = asyncio.Lock()

    async def _verdict_queue(self, project: str) -> asyncio.Queue:
        async with self._lock:
            q = self._verdicts.get(project)
            if q is None:
                q = asyncio.Queue(maxsize=128)
                self._verdicts[project] = q
            return q

    async def store_request(self, project: str, request_id: str, tool_name: str,
                            description: str, input_preview: str) -> None:
        async with self._lock:
            self._pending.setdefault(project, {})[request_id] = {
                "request_id": request_id,
                "tool_name": tool_name,
                "description": description,
                "input_preview": input_preview,
                "created_ts": time.time(),
                "project": project,
            }
        logger.info("permissions: stored %s/%s tool=%s", project, request_id, tool_name)

    def list_pending(self, project: str | None = None) -> list[dict[str, Any]]:
        out = []
        now = time.time()
        for proj, reqs in self._pending.items():
            if project is not None and proj != project:
                continue
            for r in reqs.values():
                out.append({**r, "age_seconds": round(now - r["created_ts"], 1)})
        return sorted(out, key=lambda r: r["created_ts"])

    async def respond(self, project: str, behavior: str,
                      request_id: str | None = None) -> dict[str, Any] | None:
        """Resolve a pending request. If request_id is None, picks the oldest
        pending for that project — convenient for voice "tak tak tak" flow where
        saying the request_id is impractical.
        Returns the resolved request dict (with behavior + resolved_ts), or None
        if nothing pending."""
        if behavior not in ("allow", "deny"):
            raise ValueError(f"behavior must be allow|deny, got {behavior!r}")
        async with self._lock:
            reqs = self._pending.get(project) or {}
            if not reqs:
                return None
            if request_id is None:
                # oldest
                request_id = min(reqs, key=lambda rid: reqs[rid]["created_ts"])
            req = reqs.pop(request_id, None)
            if req is None:
                return None
            if not reqs:
                self._pending.pop(project, None)
            resolved = {**req, "behavior": behavior, "resolved_ts": time.time()}
            self._history.append(resolved)
            if len(self._history) > self._history_cap:
                self._history = self._history[-self._history_cap:]
        q = await self._verdict_queue(project)
        try:
            q.put_nowait({"request_id": request_id, "behavior": behavior})
        except asyncio.QueueFull:
            logger.error("permissions: verdict queue full for %s, dropping", project)
            return None
        logger.info("permissions: resolved %s/%s -> %s", project, request_id, behavior)
        return resolved

    async def pull_verdict(self, project: str, timeout: float) -> dict[str, Any] | None:
        q = await self._verdict_queue(project)
        try:
            return await asyncio.wait_for(q.get(), timeout=timeout)
        except asyncio.TimeoutError:
            return None

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._history[-limit:])


def announce_template(project: str, tool_name: str, description: str,
                      language: str = "pl") -> str:
    """TTS announcement text. Keep short — STT/listener is the bottleneck."""
    if language == "pl":
        return (
            f"Claude w {project} chce uruchomic {tool_name}: {description}. "
            "Powiedz 'tak tak tak' aby zaakceptowac, 'nie nie nie' aby odrzucic."
        )
    return (
        f"Claude in {project} wants to run {tool_name}: {description}. "
        "Say 'yes yes yes' to allow, 'no no no' to deny."
    )
