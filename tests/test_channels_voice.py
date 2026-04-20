"""STT + routing endpoint: /channels/voice picks between push / permission-allow / deny."""
import io

from fastapi.testclient import TestClient

from voice_inbox.channels_bridge import ChannelsBridge
from voice_inbox.channels_permissions import PermissionsBroker
from voice_inbox.server import _normalize_verdict, make_app


# --- verdict regex ---------------------------------------------------------

def test_normalize_verdict_plain_tak_tak_tak():
    assert _normalize_verdict("tak tak tak") == "allow"


def test_normalize_verdict_handles_commas_and_punctuation():
    assert _normalize_verdict("Tak, tak, tak!") == "allow"
    assert _normalize_verdict("nie. nie. nie") == "deny"


def test_normalize_verdict_extra_words_around_match():
    assert _normalize_verdict("no dobra tak tak tak zatwierdzam") == "allow"


def test_normalize_verdict_english_yes_no():
    assert _normalize_verdict("yes yes yes") == "allow"
    assert _normalize_verdict("no no no") == "deny"


def test_normalize_verdict_single_tak_is_not_a_match():
    assert _normalize_verdict("tak, rob to") is None


def test_normalize_verdict_empty():
    assert _normalize_verdict("") is None


# --- /channels/voice endpoint ---------------------------------------------

class _FakeSTT:
    def __init__(self, text): self.text = text
    def transcribe(self, audio, filename="x.webm", language=None):
        return self.text


def _client(transcript: str, with_bridge=True, with_perm=True):
    bridge = ChannelsBridge() if with_bridge else None
    broker = PermissionsBroker() if with_perm else None
    app = make_app(
        channels_bridge=bridge,
        permissions_broker=broker,
        stt_client=_FakeSTT(transcript),
    )
    return TestClient(app), bridge, broker


def _upload(c, project="p", audio=b"fakeaudio"):
    return c.post("/channels/voice", files={"audio": ("clip.webm", io.BytesIO(audio), "audio/webm")},
                  data={"project": project})


def test_voice_routes_prompt_to_channel_push():
    import asyncio
    c, bridge, _ = _client("sprawdz pliki w tym katalogu")
    r = _upload(c, project="ozebud")
    assert r.status_code == 200
    body = r.json()
    assert body["action"] == "push"
    assert body["transcript"] == "sprawdz pliki w tym katalogu"
    msg = asyncio.run(bridge.pull("ozebud", timeout=0.5))
    assert msg["text"] == "sprawdz pliki w tym katalogu"


def test_voice_routes_tak_tak_tak_to_permission_allow():
    import asyncio
    c, _, broker = _client("tak tak tak")
    # seed a pending so respond has something
    asyncio.run(broker.store_request("ozebud", "abcde", "Bash", "ls", ""))
    r = _upload(c, project="ozebud")
    body = r.json()
    assert body["action"] == "permission_allow"
    assert body["resolved"]["behavior"] == "allow"
    assert body["resolved"]["request_id"] == "abcde"


def test_voice_routes_nie_nie_nie_to_permission_deny():
    import asyncio
    c, _, broker = _client("nie nie nie")
    asyncio.run(broker.store_request("ozebud", "fghij", "Bash", "rm", ""))
    r = _upload(c, project="ozebud")
    body = r.json()
    assert body["action"] == "permission_deny"
    assert body["resolved"]["behavior"] == "deny"


def test_voice_allow_without_pending_still_ok():
    c, _, _ = _client("tak tak tak")
    r = _upload(c, project="ozebud")
    body = r.json()
    assert body["action"] == "permission_allow"
    assert body["resolved"] is None


def test_voice_empty_transcript_returns_empty_action():
    c, _, _ = _client("   ")
    r = _upload(c, project="p")
    assert r.json()["action"] == "empty"


def test_voice_503_when_stt_disabled():
    app = make_app(channels_bridge=ChannelsBridge(), permissions_broker=PermissionsBroker())
    c = TestClient(app)
    r = c.post("/channels/voice", files={"audio": ("x.webm", io.BytesIO(b"x"), "audio/webm")},
               data={"project": "p"})
    assert r.status_code == 503
