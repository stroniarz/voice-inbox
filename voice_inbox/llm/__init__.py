import os
from .base import LLMClient


def make_llm(cfg: dict) -> LLMClient:
    provider = (cfg.get("provider") or "anthropic").lower()
    model = cfg.get("model")
    if not model:
        raise ValueError("llm.model is required")

    api_key_env = cfg.get("api_key_env")
    api_key = os.environ.get(api_key_env) if api_key_env else None
    base_url = cfg.get("base_url")

    if provider == "anthropic":
        if not api_key:
            raise ValueError(f"Anthropic requires env {api_key_env or 'ANTHROPIC_API_KEY'}")
        from .anthropic_llm import AnthropicLLM
        return AnthropicLLM(api_key=api_key, model=model)

    if provider in ("openai", "openrouter", "deepseek", "ollama"):
        if provider == "ollama" and not base_url:
            base_url = "http://localhost:11434/v1"
        if provider == "openrouter" and not base_url:
            base_url = "https://openrouter.ai/api/v1"
        if provider == "deepseek" and not base_url:
            base_url = "https://api.deepseek.com/v1"
        if not api_key:
            api_key = "ollama" if provider == "ollama" else None
        if not api_key:
            raise ValueError(f"{provider} requires env {api_key_env}")
        from .openai_compat import OpenAICompatLLM
        return OpenAICompatLLM(api_key=api_key, model=model, base_url=base_url)

    raise ValueError(f"Unknown LLM provider: {provider}")
