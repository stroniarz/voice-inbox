"""CCHandler — event routing, cooldown, transcript summary integration."""
import pytest

from voice_inbox.cc.handler import CCHandler


def _make(store, worker, summarizer=None, **kw):
    defaults = dict(
        stop_min_duration_seconds=0,
        cooldown_seconds=0,
        transcript_summarizer=summarizer,
        summary_min_duration_seconds=0,
    )
    defaults.update(kw)
    return CCHandler(store, worker, "pl", **defaults)


def test_notification_is_critical(store, worker):
    h = _make(store, worker)
    h({"hook_event_name": "Notification",
       "cwd": "/home/u/Projects/my-repo",
       "session_id": "s1",
       "message": "wymaga zgody na Bash"})
    assert len(worker.calls) == 1
    tag, text = worker.calls[0]
    assert tag == "critical"
    assert "my-repo" in text
    assert "wymaga zgody na Bash" in text


def test_stop_ignored_if_no_session_start_but_still_announced_when_duration_zero(store, worker):
    # With stop_min_duration=0 and no tracked start, Stop is announced
    h = _make(store, worker)
    h({"hook_event_name": "Stop",
       "cwd": "/home/u/Projects/foo",
       "session_id": "s1"})
    assert len(worker.calls) == 1
    assert "foo" in worker.calls[0][1]


def test_stop_duration_filter(store, worker):
    """When we have a session_start, short sessions are filtered out."""
    h = _make(store, worker, stop_min_duration_seconds=10)
    # Track start
    h({"hook_event_name": "UserPromptSubmit",
       "cwd": "/home/u/Projects/foo",
       "session_id": "s1"})
    # Immediate Stop — < 10s
    h({"hook_event_name": "Stop",
       "cwd": "/home/u/Projects/foo",
       "session_id": "s1"})
    assert worker.calls == []


def test_subagent_stop(store, worker):
    h = _make(store, worker)
    h({"hook_event_name": "SubagentStop",
       "cwd": "/home/u/Projects/foo",
       "session_id": "s1"})
    assert len(worker.calls) == 1
    assert "subagent" in worker.calls[0][1].lower()
    assert worker.calls[0][0] == "default"


def test_cooldown_skips_duplicates(store, worker):
    h = _make(store, worker, cooldown_seconds=60)
    h({"hook_event_name": "Stop", "cwd": "/p/repo", "session_id": "x"})
    h({"hook_event_name": "Stop", "cwd": "/p/repo", "session_id": "y"})
    # Second Stop in same project within cooldown is skipped
    assert len(worker.calls) == 1


def test_unknown_event_ignored(store, worker):
    h = _make(store, worker)
    h({"hook_event_name": "UnknownEvent", "cwd": "/p/repo", "session_id": "s1"})
    assert worker.calls == []


def test_ignore_events_config(store, worker):
    h = _make(store, worker, ignore_events=("SubagentStop",))
    h({"hook_event_name": "SubagentStop", "cwd": "/p/repo", "session_id": "s1"})
    assert worker.calls == []


def test_archives_event_with_project(store, worker):
    h = _make(store, worker)
    h({"hook_event_name": "Notification",
       "cwd": "/home/u/Projects/ircsklep",
       "session_id": "s1",
       "message": "help"})
    events = store.recent_events(hours=1)
    assert len(events) == 1
    assert events[0]["project"] == "ircsklep"
    assert events[0]["source"] == "claude_code"


def test_transcript_summary_replaces_generic(store, worker):
    class FakeSummer:
        def summarize(self, path, project, session_id=None):
            return "dodał autentykację JWT"

    h = _make(store, worker, summarizer=FakeSummer())
    h({"hook_event_name": "UserPromptSubmit",
       "cwd": "/p/ircsklep", "session_id": "s1",
       "transcript_path": "/tmp/fake.jsonl"})
    h({"hook_event_name": "Stop",
       "cwd": "/p/ircsklep", "session_id": "s1"})
    assert len(worker.calls) == 1
    text = worker.calls[0][1]
    assert "ircsklep" in text
    assert "JWT" in text


def test_transcript_summary_fallback_to_generic_on_none(store, worker):
    class NullSummer:
        def summarize(self, path, project, session_id=None):
            return None  # SKIP path

    h = _make(store, worker, summarizer=NullSummer())
    h({"hook_event_name": "UserPromptSubmit",
       "cwd": "/p/foo", "session_id": "s1",
       "transcript_path": "/tmp/fake.jsonl"})
    h({"hook_event_name": "Stop",
       "cwd": "/p/foo", "session_id": "s1"})
    assert len(worker.calls) == 1
    # Generic announcement, no summary
    assert "zakończona" in worker.calls[0][1] or "long" in worker.calls[0][1]
