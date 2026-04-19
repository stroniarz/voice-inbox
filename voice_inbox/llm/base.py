from typing import Protocol


class LLMClient(Protocol):
    def chat(self, system: str, user: str, max_tokens: int = 600) -> str:
        ...
