"""Channels bridge — queue semantics, register/active, pull timeout, HTTP wiring.

Uses asyncio.run() for the bridge's async API so no pytest-asyncio dep is needed.
"""
import asyncio
import time

from fastapi.testclient import TestClient

from voice_inbox.channels_bridge import ChannelsBridge
from voice_inbox.server import make_app


def run(coro):
    return asyncio.get_event_loop().run_until_complete(coro) if False else asyncio.run(coro)


def test_push_pull_roundtrip():
    async def body():
        b = ChannelsBridge()
        await b.register("alpha", cwd="/tmp/alpha")
        await b.push("alpha", "hello", meta={"k": "v"})
        return await b.pull("alpha", timeout=1.0)
    assert run(body()) == {"text": "hello", "meta": {"k": "v"}}


def test_pull_timeout_returns_none_without_blocking_forever():
    async def body():
        b = ChannelsBridge()
        start = time.monotonic()
        msg = await b.pull("empty", timeout=0.2)
        return msg, time.monotonic() - start
    msg, elapsed = run(body())
    assert msg is None
    assert elapsed < 1.0


def test_push_to_wrong_project_does_not_leak():
    async def body():
        b = ChannelsBridge()
        await b.push("alpha", "a-msg")
        await b.push("beta", "b-msg")
        a = await b.pull("alpha", timeout=0.5)
        c = await b.pull("beta", timeout=0.5)
        return a, c
    a, c = run(body())
    assert a["text"] == "a-msg"
    assert c["text"] == "b-msg"


def test_active_projects_honours_ttl():
    async def body():
        b = ChannelsBridge(heartbeat_ttl=0.1)
        await b.register("fresh", cwd="/x")
        before = b.active_projects()
        await asyncio.sleep(0.15)
        after = b.active_projects()
        return before, after
    before, after = run(body())
    assert any(p["project"] == "fresh" for p in before)
    assert not any(p["project"] == "fresh" for p in after)


def test_push_empty_meta_defaults_to_empty_dict():
    async def body():
        b = ChannelsBridge()
        await b.push("alpha", "x")
        return await b.pull("alpha", timeout=0.5)
    msg = run(body())
    assert msg["meta"] == {}


def test_queue_full_returns_false():
    async def body():
        b = ChannelsBridge()
        b._queues["p"] = asyncio.Queue(maxsize=1)
        a = await b.push("p", "first")
        c = await b.push("p", "second")
        return a, c
    a, c = run(body())
    assert a is True
    assert c is False


# --- HTTP endpoint wiring ---------------------------------------------------

def _app_with_bridge():
    return make_app(channels_bridge=ChannelsBridge())


def test_endpoints_return_503_when_disabled():
    c = TestClient(make_app())
    assert c.post("/channels/register", json={"project": "x"}).status_code == 503
    assert c.post("/channels/push", json={"project": "x", "text": "t"}).status_code == 503
    assert c.get("/channels/pull", params={"project": "x"}).status_code == 503
    assert c.get("/channels/active").status_code == 503


def test_http_register_and_active():
    c = TestClient(_app_with_bridge())
    r = c.post("/channels/register", json={"project": "ozebud", "cwd": "/Users/x/ozebud"})
    assert r.status_code == 200
    names = [p["project"] for p in c.get("/channels/active").json()["projects"]]
    assert "ozebud" in names


def test_http_push_then_pull():
    c = TestClient(_app_with_bridge())
    c.post("/channels/register", json={"project": "ozebud"})
    c.post("/channels/push", json={"project": "ozebud", "text": "list files"})
    r = c.get("/channels/pull", params={"project": "ozebud", "timeout": 1.0})
    assert r.status_code == 200
    assert r.json()["message"]["text"] == "list files"


def test_http_pull_timeout_returns_204():
    c = TestClient(_app_with_bridge())
    r = c.get("/channels/pull", params={"project": "nobody", "timeout": 0.2})
    assert r.status_code == 204


def test_http_pull_clamps_huge_timeout():
    c = TestClient(_app_with_bridge())
    c.post("/channels/push", json={"project": "p", "text": "t"})
    r = c.get("/channels/pull", params={"project": "p", "timeout": 999.0})
    assert r.status_code == 200


# --- /channels/reply (phase 3 — speak tool) --------------------------------

class _SpyWorker:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def enqueue(self, text, tag="default"):
        self.calls.append((tag, text))


class _SpyStore:
    def __init__(self):
        self.events: list[dict] = []

    def archive_event(self, source, external_id, author, short, title, body, project=None):
        self.events.append({
            "source": source, "external_id": external_id, "author": author,
            "short": short, "title": title, "body": body, "project": project,
        })


def test_reply_enqueues_tts_and_archives_by_default():
    worker = _SpyWorker()
    store = _SpyStore()
    c = TestClient(make_app(channels_bridge=ChannelsBridge(), tts_worker=worker, store=store))
    r = c.post("/channels/reply", json={"project": "ozebud", "text": "zrobione"})
    assert r.status_code == 200
    body = r.json()
    assert body == {"ok": True, "spoken": True, "archived": True}
    assert worker.calls == [("default", "zrobione")]
    assert len(store.events) == 1
    ev = store.events[0]
    assert ev["source"] == "cc-reply"
    assert ev["project"] == "ozebud"
    assert ev["body"] == "zrobione"


def test_reply_skips_archive_when_disabled():
    worker = _SpyWorker()
    store = _SpyStore()
    c = TestClient(make_app(
        channels_bridge=ChannelsBridge(), tts_worker=worker, store=store,
        archive_replies=False,
    ))
    r = c.post("/channels/reply", json={"project": "p", "text": "hi"})
    assert r.json() == {"ok": True, "spoken": True, "archived": False}
    assert store.events == []


def test_reply_without_tts_worker_still_ok():
    c = TestClient(make_app(channels_bridge=ChannelsBridge()))
    r = c.post("/channels/reply", json={"project": "p", "text": "x"})
    assert r.json()["ok"] is True
    assert r.json()["spoken"] is False


def test_reply_empty_text_returns_400():
    c = TestClient(make_app(channels_bridge=ChannelsBridge()))
    r = c.post("/channels/reply", json={"project": "p", "text": "   "})
    assert r.status_code == 400


def test_reply_without_bridge_is_not_blocked():
    # reply should work independently of bridge presence — different concern
    worker = _SpyWorker()
    c = TestClient(make_app(tts_worker=worker))
    r = c.post("/channels/reply", json={"project": "p", "text": "hi"})
    assert r.status_code == 200
