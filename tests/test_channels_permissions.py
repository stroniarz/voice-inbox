"""Permission relay broker — request/respond/poll/history semantics + HTTP wiring."""
import asyncio
import time

from fastapi.testclient import TestClient

from voice_inbox.channels_permissions import PermissionsBroker, announce_template
from voice_inbox.server import make_app


def run(coro):
    return asyncio.run(coro)


# --- broker unit ------------------------------------------------------------

def test_store_and_list_pending():
    async def body():
        b = PermissionsBroker()
        await b.store_request("ozebud", "abcde", "Bash", "list files", "ls -la")
        await b.store_request("other", "fghij", "Write", "create file", "/tmp/x")
        return b.list_pending(), b.list_pending(project="ozebud")
    all_pending, oz_pending = run(body())
    assert len(all_pending) == 2
    assert len(oz_pending) == 1
    assert oz_pending[0]["request_id"] == "abcde"
    assert oz_pending[0]["tool_name"] == "Bash"
    assert "age_seconds" in oz_pending[0]


def test_respond_by_explicit_request_id_returns_resolved_and_removes_pending():
    async def body():
        b = PermissionsBroker()
        await b.store_request("ozebud", "abcde", "Bash", "ls", "ls -la")
        resolved = await b.respond("ozebud", "allow", request_id="abcde")
        return resolved, b.list_pending()
    resolved, pending = run(body())
    assert resolved["behavior"] == "allow"
    assert resolved["request_id"] == "abcde"
    assert "resolved_ts" in resolved
    assert pending == []


def test_respond_without_request_id_picks_oldest():
    async def body():
        b = PermissionsBroker()
        await b.store_request("ozebud", "old00", "Bash", "first", "")
        await asyncio.sleep(0.01)
        await b.store_request("ozebud", "new00", "Bash", "second", "")
        resolved = await b.respond("ozebud", "allow")
        return resolved, b.list_pending()
    resolved, pending = run(body())
    assert resolved["request_id"] == "old00"
    assert len(pending) == 1
    assert pending[0]["request_id"] == "new00"


def test_respond_with_invalid_behavior_raises():
    async def body():
        b = PermissionsBroker()
        await b.store_request("ozebud", "abcde", "Bash", "ls", "")
        try:
            await b.respond("ozebud", "maybe", request_id="abcde")
        except ValueError as e:
            return str(e)
        return "no-raise"
    err = run(body())
    assert "allow|deny" in err


def test_respond_with_no_pending_returns_none():
    async def body():
        b = PermissionsBroker()
        return await b.respond("ozebud", "allow")
    assert run(body()) is None


def test_pull_verdict_after_respond():
    async def body():
        b = PermissionsBroker()
        await b.store_request("ozebud", "abcde", "Bash", "ls", "")
        await b.respond("ozebud", "allow", request_id="abcde")
        return await b.pull_verdict("ozebud", timeout=0.5)
    v = run(body())
    assert v == {"request_id": "abcde", "behavior": "allow"}


def test_pull_verdict_timeout_is_none():
    async def body():
        b = PermissionsBroker()
        start = time.monotonic()
        v = await b.pull_verdict("ozebud", timeout=0.2)
        return v, time.monotonic() - start
    v, elapsed = run(body())
    assert v is None
    assert elapsed < 1.0


def test_verdicts_are_project_scoped():
    async def body():
        b = PermissionsBroker()
        await b.store_request("a", "rid-a", "Bash", "a", "")
        await b.store_request("b", "rid-b", "Bash", "b", "")
        await b.respond("a", "allow", request_id="rid-a")
        await b.respond("b", "deny", request_id="rid-b")
        va = await b.pull_verdict("a", timeout=0.5)
        vb = await b.pull_verdict("b", timeout=0.5)
        return va, vb
    va, vb = run(body())
    assert va == {"request_id": "rid-a", "behavior": "allow"}
    assert vb == {"request_id": "rid-b", "behavior": "deny"}


def test_history_captures_resolved_with_latency():
    async def body():
        b = PermissionsBroker()
        await b.store_request("p", "abcde", "Bash", "ls", "")
        await asyncio.sleep(0.05)
        await b.respond("p", "allow", request_id="abcde")
        return b.history()
    h = run(body())
    assert len(h) == 1
    entry = h[0]
    assert entry["behavior"] == "allow"
    assert entry["resolved_ts"] > entry["created_ts"]


def test_announce_template_polish_mentions_tak_tak_tak():
    msg = announce_template("ozebud", "Bash", "ls files", language="pl")
    assert "ozebud" in msg
    assert "Bash" in msg
    assert "tak tak tak" in msg
    assert "nie nie nie" in msg


def test_announce_template_english_fallback():
    msg = announce_template("proj", "Write", "create file", language="en")
    assert "yes yes yes" in msg
    assert "no no no" in msg


# --- HTTP endpoint wiring ---------------------------------------------------

class _SpyWorker:
    def __init__(self): self.calls: list[tuple[str, str]] = []
    def enqueue(self, text, tag="default"): self.calls.append((tag, text))


class _SpyStore:
    def __init__(self): self.events: list[dict] = []
    def archive_event(self, source, external_id, author, short, title, body, project=None):
        self.events.append({"source": source, "project": project, "short": short})


def _app(broker=None, worker=None, store=None, archive=True, lang="pl"):
    return make_app(
        permissions_broker=broker if broker is not None else PermissionsBroker(),
        tts_worker=worker,
        store=store,
        archive_permissions=archive,
        permissions_language=lang,
    )


def test_endpoints_return_503_when_broker_disabled():
    c = TestClient(make_app())
    assert c.post("/channels/permissions/request",
                  json={"project": "p", "request_id": "r", "tool_name": "t",
                        "description": "d", "input_preview": ""}).status_code == 503
    assert c.get("/channels/permissions/pending").status_code == 503
    assert c.post("/channels/permissions/respond",
                  json={"project": "p", "behavior": "allow"}).status_code == 503
    assert c.get("/channels/permissions/poll", params={"project": "p"}).status_code == 503
    assert c.get("/channels/permissions/log").status_code == 503


def test_http_request_triggers_tts_announce_and_archive():
    worker = _SpyWorker()
    store = _SpyStore()
    c = TestClient(_app(worker=worker, store=store))
    r = c.post("/channels/permissions/request", json={
        "project": "ozebud", "request_id": "abcde",
        "tool_name": "Bash", "description": "list files",
        "input_preview": "ls -la",
    })
    assert r.status_code == 200
    assert len(worker.calls) == 1
    assert worker.calls[0][0] == "critical"  # critical tag for permission prompts
    assert "Bash" in worker.calls[0][1]
    assert "tak tak tak" in worker.calls[0][1]
    assert len(store.events) == 1
    assert store.events[0]["source"] == "cc-permission-request"


def test_http_respond_resolves_and_archives():
    worker = _SpyWorker()
    store = _SpyStore()
    c = TestClient(_app(worker=worker, store=store))
    c.post("/channels/permissions/request", json={
        "project": "p", "request_id": "abcde", "tool_name": "Bash",
        "description": "d", "input_preview": "",
    })
    r = c.post("/channels/permissions/respond", json={"project": "p", "behavior": "allow"})
    assert r.status_code == 200
    resolved = r.json()["resolved"]
    assert resolved["behavior"] == "allow"
    response_events = [e for e in store.events if e["source"] == "cc-permission-response"]
    assert len(response_events) == 1


def test_http_respond_no_pending_returns_404():
    c = TestClient(_app())
    r = c.post("/channels/permissions/respond", json={"project": "p", "behavior": "allow"})
    assert r.status_code == 404


def test_http_respond_invalid_behavior_returns_400():
    broker = PermissionsBroker()
    c = TestClient(_app(broker=broker))
    r = c.post("/channels/permissions/respond",
               json={"project": "p", "behavior": "maybe"})
    # Pydantic coerces or FastAPI route returns 400 via our explicit check
    assert r.status_code == 400


def test_http_poll_timeout_returns_204():
    c = TestClient(_app())
    r = c.get("/channels/permissions/poll", params={"project": "p", "timeout": 0.2})
    assert r.status_code == 204


def test_http_poll_after_respond_returns_verdict():
    c = TestClient(_app())
    c.post("/channels/permissions/request", json={
        "project": "p", "request_id": "abcde", "tool_name": "Bash",
        "description": "d", "input_preview": "",
    })
    c.post("/channels/permissions/respond", json={"project": "p", "behavior": "deny"})
    r = c.get("/channels/permissions/poll", params={"project": "p", "timeout": 1.0})
    assert r.status_code == 200
    assert r.json()["verdict"] == {"request_id": "abcde", "behavior": "deny"}


def test_http_pending_filter_by_project():
    c = TestClient(_app())
    c.post("/channels/permissions/request", json={
        "project": "a", "request_id": "r1", "tool_name": "Bash",
        "description": "d", "input_preview": "",
    })
    c.post("/channels/permissions/request", json={
        "project": "b", "request_id": "r2", "tool_name": "Bash",
        "description": "d", "input_preview": "",
    })
    all_p = c.get("/channels/permissions/pending").json()["pending"]
    a_p = c.get("/channels/permissions/pending", params={"project": "a"}).json()["pending"]
    assert len(all_p) == 2
    assert len(a_p) == 1
    assert a_p[0]["project"] == "a"


def test_http_log_returns_resolved_history():
    c = TestClient(_app())
    c.post("/channels/permissions/request", json={
        "project": "p", "request_id": "abcde", "tool_name": "Bash",
        "description": "d", "input_preview": "",
    })
    c.post("/channels/permissions/respond", json={"project": "p", "behavior": "allow"})
    log = c.get("/channels/permissions/log").json()["history"]
    assert len(log) == 1
    assert log[0]["behavior"] == "allow"
