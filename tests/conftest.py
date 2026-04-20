import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from voice_inbox.dedup import DedupStore  # noqa: E402


class MockLLM:
    """Reusable mock LLM — collects calls, returns configurable answer."""

    def __init__(self, answer: str = "mock answer"):
        self.answer = answer
        self.calls: list[tuple[str, str, int]] = []

    def chat(self, system: str, user: str, max_tokens: int = 600) -> str:
        self.calls.append((system, user, max_tokens))
        return self.answer


class MockWorker:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []  # (tag, text)

    def enqueue(self, text: str, tag: str = "default") -> None:
        self.calls.append((tag, text))


@pytest.fixture
def store(tmp_path):
    return DedupStore(tmp_path / "test.db")


@pytest.fixture
def mock_llm():
    return MockLLM()


@pytest.fixture
def worker():
    return MockWorker()
