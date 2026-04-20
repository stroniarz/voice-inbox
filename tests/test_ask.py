"""AskHandler — context building, LLM invocation, project filtering."""

from voice_inbox.ask import AskHandler


def test_build_context_empty_store(store, mock_llm):
    h = AskHandler(mock_llm, store, "pl")
    ctx = h.build_context()
    assert "Brak" in ctx or "No" in ctx


def test_build_context_with_events(store, mock_llm):
    store.archive_event("linear", "a", "Alice", "nowe zadanie: fix bug",
                        "[STR-1] fix bug", "desc", project="STR")
    store.archive_event("claude_code", "b", "cc", "Claude w foo skończył",
                        "Stop", "", project="foo")
    h = AskHandler(mock_llm, store, "pl")
    ctx = h.build_context()
    assert "STR" in ctx
    assert "foo" in ctx
    assert "linear" in ctx
    assert "claude_code" in ctx


def test_ask_passes_context_to_llm(store, mock_llm):
    store.archive_event("linear", "a", "u", "fix bug", "[X-1] bug", "",
                        project="X")
    h = AskHandler(mock_llm, store, "pl")
    answer = h.ask("co słychać?")
    assert answer == "mock answer"
    # LLM was called exactly once with a system prompt + user payload
    # containing context and the question
    assert len(mock_llm.calls) == 1
    system, user_content, _ = mock_llm.calls[0]
    assert "audio" in system.lower() or "TTS" in system
    assert "co słychać?" in user_content
    assert "X-1" in user_content or "fix bug" in user_content


def test_ask_with_project_filter(store, mock_llm):
    store.archive_event("linear", "a", "u", "STR task", "[STR-1]", "",
                        project="STR")
    store.archive_event("linear", "b", "u", "IRC task", "[IRC-1]", "",
                        project="IRC")
    h = AskHandler(mock_llm, store, "pl")
    h.ask("co w STR?", project="STR")
    _, user_content, _ = mock_llm.calls[0]
    # Context should include STR but not IRC
    assert "STR-1" in user_content
    assert "IRC-1" not in user_content


def test_ask_handles_llm_exception(store):
    class BrokenLLM:
        def chat(self, s, u, max_tokens=600):
            raise RuntimeError("boom")

    h = AskHandler(BrokenLLM(), store, "pl")
    answer = h.ask("co słychać?")
    # Returns graceful error text, doesn't raise
    assert "spróbuj" in answer.lower() or "try" in answer.lower()
