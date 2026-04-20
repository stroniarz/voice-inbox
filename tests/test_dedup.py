"""DedupStore — seen tracking, cursors, events archive + project column."""


def test_is_seen_roundtrip(store):
    assert not store.is_seen("linear", "e1")
    store.mark_seen("linear", "e1")
    assert store.is_seen("linear", "e1")
    assert not store.is_seen("linear", "e2")
    # Mark twice is idempotent (OR IGNORE)
    store.mark_seen("linear", "e1")


def test_cursor_roundtrip(store):
    assert store.get_cursor("linear") is None
    store.set_cursor("linear", "2026-01-01T00:00:00Z")
    assert store.get_cursor("linear") == "2026-01-01T00:00:00Z"
    # Update
    store.set_cursor("linear", "2026-02-01T00:00:00Z")
    assert store.get_cursor("linear") == "2026-02-01T00:00:00Z"


def test_archive_event_with_project(store):
    store.archive_event("linear", "e1", "Alice", "short text",
                        "[STR-1] title", "body", project="STR")
    events = store.recent_events(hours=1)
    assert len(events) == 1
    assert events[0]["project"] == "STR"
    assert events[0]["source"] == "linear"
    assert events[0]["short"] == "short text"


def test_archive_event_without_project(store):
    store.archive_event("slack", "e1", "bot", "dm", "title", "body")
    events = store.recent_events(hours=1)
    assert events[0]["project"] is None


def test_recent_events_project_filter(store):
    store.archive_event("linear", "a", "u", "s", "t", "b", project="STR")
    store.archive_event("linear", "b", "u", "s", "t", "b", project="IRC")
    store.archive_event("claude_code", "c", "u", "s", "t", "b", project="IRC")

    all_ = store.recent_events(hours=1)
    assert len(all_) == 3

    irc = store.recent_events(hours=1, project="IRC")
    assert len(irc) == 2
    assert {e["source"] for e in irc} == {"linear", "claude_code"}


def test_project_summary_grouping(store):
    store.archive_event("linear", "a", "u", "s", "t", "b", project="STR")
    store.archive_event("linear", "b", "u", "s", "t", "b", project="STR")
    store.archive_event("claude_code", "c", "u", "s", "t", "b", project="STR")

    summary = store.project_summary(hours=1)
    # Grouped by (project, source): STR+linear=2, STR+claude_code=1
    groups = {(row["project"], row["source"]): row["count"] for row in summary}
    assert groups[("STR", "linear")] == 2
    assert groups[("STR", "claude_code")] == 1


def test_fetch_undigested(store):
    store.archive_event("linear", "a", "u", "s", "t", "b", project="STR")
    store.archive_event("linear", "b", "u", "s", "t", "b", project="STR")
    events = store.fetch_undigested(since_minutes=60)
    assert len(events) == 2
    store.mark_digested([events[0]["id"]])
    events2 = store.fetch_undigested(since_minutes=60)
    assert len(events2) == 1
    assert events2[0]["id"] == events[1]["id"]


def test_migration_idempotent(tmp_path):
    """DedupStore.__init__ runs multiple times without errors — migration is conditional."""
    from voice_inbox.dedup import DedupStore

    db = tmp_path / "t.db"
    DedupStore(db)
    DedupStore(db)  # should not raise — project column already present
    DedupStore(db)
