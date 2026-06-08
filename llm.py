"""
LLM factory.

- No module-level globals that mutate on first call.
- `build_llm()` is cheap to call repeatedly — LangChain's init_chat_model
  is already idempotent for the same args.
- Callers bind tools themselves so this module stays ignorant of tool lists.
"""
from __future__ import annotations

from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel

from config import MODEL, MODEL_PROVIDER, OPENAI_API_BASE, OPENAI_API_KEY


def build_llm(temperature: float = 0.5) -> BaseChatModel:
    """Return a bare (no tools bound) chat model."""
    return init_chat_model(
        MODEL,
        api_key=OPENAI_API_KEY,
        base_url=OPENAI_API_BASE,
        model_provider=MODEL_PROVIDER,
        temperature=temperature,
    )