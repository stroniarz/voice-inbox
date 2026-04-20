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
