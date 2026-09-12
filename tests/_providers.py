"""Stub LLM providers that record every prompt they receive.

``SpyProvider`` stands in for a cloud provider; ``SpyLocalProvider`` is a real
``LocalProvider`` subclass (so ``isinstance`` checks see it as local) that never
touches Ollama.  Tests assert on ``.prompts`` to prove what did or did not leave
the process.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from contractex.llm.base import LLMProvider
from contractex.llm.local_provider import LocalProvider


class _Recorder:
    reply: str = "ok"
    structured: dict[str, Any] = {}

    def _init_recorder(self, reply: str = "ok", structured: dict[str, Any] | None = None) -> None:
        self.prompts: list[str] = []
        self.reply = reply
        self.structured = structured or {}

    def complete(self, prompt: str, temperature: float = 0.7, max_tokens=None, **kwargs) -> str:
        self.prompts.append(prompt)
        return self.reply

    def extract_structured(
        self, prompt: str, schema: type[BaseModel], temperature: float = 0.0, max_tokens=None
    ) -> BaseModel:
        self.prompts.append(prompt)
        return schema.model_validate(self.structured)

    def estimate_cost(self, text: str) -> float:
        return 0.0

    def count_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 100_000

    @property
    def model(self) -> str:
        return "spy"


class SpyProvider(_Recorder, LLMProvider):
    """A cloud-like provider (not a LocalProvider)."""

    def __init__(self, reply: str = "ok", structured: dict[str, Any] | None = None) -> None:
        self._init_recorder(reply, structured)


class SpyLocalProvider(_Recorder, LocalProvider):
    """A LocalProvider that records prompts instead of calling Ollama."""

    def __init__(self, reply: str = "ok", structured: dict[str, Any] | None = None) -> None:
        self._init_recorder(reply, structured)
