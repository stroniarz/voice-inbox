"""HTTP server — endpoints, routing, graceful 503 when components disabled."""
from fastapi.testclient import TestClient

from voice_inbox.server import make_app


class _MockAsk:
    def __init__(self): self.calls = []
    def ask(self, q, project=None):
        self.calls.append((q, project))
        return f"answered: {q}"


class _MockSTT:
    def __init__(self, text="hello world"): self.text = text
    def transcribe(self, audio, filename="x.wav", language=None):
        return self.text


class _MockTTS:
    def synthesize(self, text):
        return b"FAKE_WAV_BYTES", "audio/wav"


def test_health():
    app = make_app()
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_cc_event_calls_handler():
    received = []
    app = make_app(cc_handler=lambda p: received.append(p))
    c = TestClient(app)
    r = c.post("/cc-event", json={"hook_event_name": "Stop", "cwd": "/foo"})
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert received == [{"hook_event_name": "Stop", "cwd": "/foo"}]


def test_cc_event_disabled_returns_error():
    app = make_app(cc_handler=None)
    c = TestClient(app)
    r = c.post("/cc-event", json={})
    body = r.json()
    assert body["ok"] is False


def test_cc_event_handler_exception_does_not_break_response():
    def boom(_): raise RuntimeError("bang")
    app = make_app(cc_handler=boom)
    c = TestClient(app)
    r = c.post("/cc-event", json={"x": 1})
    # Server logs exception, still returns ok=true so hook doesn't break
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_ask_endpoint():
    ask = _MockAsk()
    app = make_app(ask_handler=ask)
    c = TestClient(app)
    r = c.post("/ask", json={"q": "co słychać?"})
    data = r.json()
    assert data["ok"] is True
    assert data["answer"] == "answered: co słychać?"
    assert ask.calls == [("co słychać?", None)]


def test_ask_with_project():
    ask = _MockAsk()
    app = make_app(ask_handler=ask)
    c = TestClient(app)
    c.post("/ask", json={"q": "what in IRC?", "project": "IRC"})
    assert ask.calls == [("what in IRC?", "IRC")]


def test_ask_disabled():
    app = make_app(ask_handler=None)
    c = TestClient(app)
    r = c.post("/ask", json={"q": "hi"})
    assert r.status_code == 503


def test_voice_disabled_without_stt():
    app = make_app(ask_handler=_MockAsk(), stt_client=None)
    c = TestClient(app)
    r = c.post("/voice", files={"audio": ("t.wav", b"xxx", "audio/wav")})
    assert r.status_code == 503


def test_voice_happy_path():
    ask = _MockAsk()
    app = make_app(ask_handler=ask, stt_client=_MockSTT("hello"),
                   tts_client=_MockTTS())
    c = TestClient(app)
    r = c.post("/voice", files={"audio": ("t.wav", b"abcd", "audio/wav")})
    data = r.json()
    assert data["ok"] is True
    assert data["transcript"] == "hello"
    assert data["answer"] == "answered: hello"
    assert data["mime"] == "audio/wav"
    assert data["audio_b64"]  # non-empty base64


def test_voice_with_project():
    ask = _MockAsk()
    app = make_app(ask_handler=ask, stt_client=_MockSTT("w IRC?"),
                   tts_client=_MockTTS())
    c = TestClient(app)
    c.post("/voice",
           files={"audio": ("t.wav", b"abcd", "audio/wav")},
           data={"project": "IRC"})
    assert ask.calls[-1] == ("w IRC?", "IRC")


def test_voice_empty_transcript():
    app = make_app(ask_handler=_MockAsk(), stt_client=_MockSTT(""),
                   tts_client=_MockTTS())
    c = TestClient(app)
    r = c.post("/voice", files={"audio": ("t.wav", b"abcd", "audio/wav")})
    data = r.json()
    assert data["ok"] is True
    assert data["transcript"] == ""
    assert data["answer"] == ""


def test_status_endpoint(store):
    store.archive_event("linear", "a", "u", "s", "t", "b", project="STR")
    app = make_app(store=store)
    c = TestClient(app)
    r = c.get("/status?hours=24")
    data = r.json()
    assert data["ok"] is True
    assert data["hours"] == 24
    assert len(data["events"]) == 1
    assert data["events"][0]["project"] == "STR"
    assert {p["project"] for p in data["projects"]} == {"STR"}


def test_static_mount_does_not_clobber_api(tmp_path):
    public = tmp_path / "public"
    public.mkdir()
    (public / "index.html").write_text("<html>PWA</html>")
    app = make_app(public_dir=public)
    c = TestClient(app)
    # Static root serves HTML
    r1 = c.get("/")
    assert r1.status_code == 200
    assert "PWA" in r1.text
    # API routes still work
    r2 = c.get("/health")
    assert r2.status_code == 200
    assert r2.json() == {"ok": True}
