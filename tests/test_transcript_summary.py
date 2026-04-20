"""TranscriptSummarizer — JSONL parsing, filtering, cache."""
import json
from collections import Counter
from pathlib import Path

import pytest

from voice_inbox.cc.session_summary import (
    TranscriptSummarizer,
    _extract_turns,
    _format_context,
)


def _write_jsonl(path: Path, lines: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(ln) for ln in lines) + "\n")


def test_extract_turns_basic(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_jsonl(path, [
        {"message": {"role": "user", "content": "Dodaj testy"}},
        {"message": {"role": "assistant",
                     "content": [
                         {"type": "text", "text": "OK, dodaję."},
                         {"type": "tool_use", "name": "Edit"},
                         {"type": "tool_use", "name": "Bash"},
                     ]}},
        {"message": {"role": "user", "content": "dzięki"}},
        {"message": {"role": "assistant",
                     "content": [{"type": "text", "text": "Gotowe."}]}},
    ])
    turns = _extract_turns(str(path))
    assert turns["first_prompt"] == "Dodaj testy"
    assert turns["last_prompt"] == "dzięki"
    assert dict(turns["tool_mix"]) == {"Edit": 1, "Bash": 1}
    assert turns["last_assistant_text"] == "Gotowe."
    assert turns["total_tool_uses"] == 2


def test_extract_turns_filters_system_reminders(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_jsonl(path, [
        {"message": {"role": "user", "content": "real prompt"}},
        {"message": {"role": "user",
                     "content": "<system-reminder>don't do X</system-reminder>"}},
        {"message": {"role": "user", "content": "another real one"}},
    ])
    turns = _extract_turns(str(path))
    assert turns["all_prompts"] == ["real prompt", "another real one"]


def test_extract_turns_missing_file(tmp_path):
    turns = _extract_turns(str(tmp_path / "nope.jsonl"))
    assert turns == {}


def test_extract_turns_skips_bad_json_lines(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text(
        json.dumps({"message": {"role": "user", "content": "one"}}) + "\n"
        "this is not json\n"
        + json.dumps({"message": {"role": "user", "content": "two"}}) + "\n"
    )
    turns = _extract_turns(str(path))
    assert turns["all_prompts"] == ["one", "two"]


def test_format_context_includes_prompts_and_tools(tmp_path):
    turns = {
        "first_prompt": "Dodaj testy",
        "last_prompt": "dzięki",
        "all_prompts": ["Dodaj testy", "dzięki"],
        "tool_mix": Counter({"Edit": 5, "Bash": 3}),
        "last_assistant_text": "Gotowe.",
        "total_tool_uses": 8,
    }
    ctx = _format_context(turns, project="test-project")
    assert "test-project" in ctx
    assert "Dodaj testy" in ctx
    assert "Edit 5" in ctx
    assert "Bash 3" in ctx
    assert "Gotowe." in ctx


def _FakeLLM(reply="dodał testy"):
    class L:
        def __init__(self): self.calls = []
        def chat(self, s, u, max_tokens=600):
            self.calls.append((s, u))
            return reply
    return L()


def test_summarize_returns_text_from_llm(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_jsonl(path, [
        {"message": {"role": "user", "content": "prompt 1"}},
        {"message": {"role": "user", "content": "prompt 2"}},
        {"message": {"role": "assistant",
                     "content": [{"type": "text", "text": "Made changes."},
                                 {"type": "tool_use", "name": "Edit"}]}},
    ])
    llm = _FakeLLM("dodał integrację testów")
    summer = TranscriptSummarizer(llm, "pl")
    out = summer.summarize(str(path), "foo", session_id="s1")
    assert out == "dodał integrację testów"
    assert len(llm.calls) == 1


def test_summarize_caches_per_session(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_jsonl(path, [
        {"message": {"role": "user", "content": "hi"}},
        {"message": {"role": "assistant",
                     "content": [{"type": "text", "text": "ok"},
                                 {"type": "tool_use", "name": "Bash"}]}},
    ])
    llm = _FakeLLM("summary text")
    summer = TranscriptSummarizer(llm, "pl")
    a = summer.summarize(str(path), "proj", session_id="abc")
    b = summer.summarize(str(path), "proj", session_id="abc")
    assert a == b
    assert len(llm.calls) == 1  # second call served from cache


def test_summarize_skip_returns_none(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_jsonl(path, [
        {"message": {"role": "user", "content": "hi"}},
        {"message": {"role": "assistant",
                     "content": [{"type": "text", "text": "ok"}]}},
    ])
    class SkipLLM:
        def chat(self, s, u, max_tokens=600): return "SKIP"
    summer = TranscriptSummarizer(SkipLLM(), "pl")
    assert summer.summarize(str(path), "proj") is None


def test_summarize_returns_none_for_empty_transcript(tmp_path):
    path = tmp_path / "t.jsonl"
    path.write_text("")
    summer = TranscriptSummarizer(_FakeLLM(), "pl")
    assert summer.summarize(str(path), "proj") is None


def test_summarize_strips_surrounding_quotes(tmp_path):
    path = tmp_path / "t.jsonl"
    _write_jsonl(path, [
        {"message": {"role": "user", "content": "dodaj coś sensownego żeby kontekst był długi"}},
        {"message": {"role": "assistant",
                     "content": [{"type": "text",
                                  "text": "zrobiłem to"},
                                 {"type": "tool_use", "name": "Edit"}]}},
    ])
    summer = TranscriptSummarizer(_FakeLLM('"quoted summary"'), "pl")
    out = summer.summarize(str(path), "proj")
    assert out == "quoted summary"
