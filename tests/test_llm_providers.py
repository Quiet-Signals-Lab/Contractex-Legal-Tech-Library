"""
Provider behaviour that needs no SDK and no network: LocalProvider's retry
policy and JSON parsing, and LangChainProvider's handling of temperature.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import BaseModel

from contractex.core.extraction_schemas import LLMFinancialResponse
from contractex.exceptions import LLMProviderError
from contractex.llm import local_provider
from contractex.llm.langchain_provider import LangChainProvider
from contractex.llm.local_provider import LocalProvider

# ---------------------------------------------------------------------------
# LocalProvider
# ---------------------------------------------------------------------------


class _FakeOllama:
    """Replays *replies* from ``generate``; an exception instance is raised instead."""

    def __init__(self, *replies: Any) -> None:
        self.replies = list(replies)
        self.calls: list[dict[str, Any]] = []

    def generate(self, **kwargs: Any) -> dict[str, str]:
        self.calls.append(kwargs)
        reply = self.replies[min(len(self.calls), len(self.replies)) - 1]
        if isinstance(reply, Exception):
            raise reply
        return {"response": reply if isinstance(reply, str) else json.dumps(reply)}


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    recorded: list[float] = []
    monkeypatch.setattr(local_provider.time, "sleep", recorded.append)
    return recorded


def make_local(client: _FakeOllama) -> LocalProvider:
    provider = LocalProvider.__new__(LocalProvider)  # skip the Ollama import and model check
    provider._model, provider._temperature, provider._max_tokens = "llama3.1:8b", 0.0, 4000
    provider.client = client
    return provider


TERM = {"term_type": "service_fee", "amount": "5000", "frequency": "monthly", "confidence": 0.9}


class TestLocalProviderRetries:
    def test_schema_mismatch_is_not_retried(self, sleeps):
        client = _FakeOllama({"financial_terms": [{"amount": "5000"}]})  # term_type missing
        with pytest.raises(LLMProviderError, match="validation error"):
            make_local(client).extract_structured("prompt", LLMFinancialResponse)
        assert len(client.calls) == 1
        assert sleeps == []

    def test_invalid_json_is_not_retried(self, sleeps):
        client = _FakeOllama('{"financial_terms": [')
        with pytest.raises(LLMProviderError, match="Local LLM structured extraction failed"):
            make_local(client).extract_structured("prompt", LLMFinancialResponse)
        assert len(client.calls) == 1
        assert sleeps == []

    def test_transient_error_is_still_retried(self, sleeps):
        client = _FakeOllama(ConnectionError("model is loading"), {"financial_terms": [TERM]})
        result = make_local(client).extract_structured("prompt", LLMFinancialResponse)
        assert isinstance(result, LLMFinancialResponse) and len(result.financial_terms) == 1
        assert len(client.calls) == 2
        assert sleeps == [2.0]

    def test_persistent_transient_error_gives_up_after_three_attempts(self, sleeps):
        client = _FakeOllama(ConnectionError("connection refused"))
        with pytest.raises(LLMProviderError, match="after 3 retries"):
            make_local(client).complete("prompt")
        assert len(client.calls) == 3
        assert sleeps == [2.0, 4.0]


class TestLocalProviderParsing:
    def test_null_for_a_defaulted_field_takes_the_default(self, sleeps):
        term = {**TERM, "currency": None, "description": None, "conditions": None}
        client = _FakeOllama({"financial_terms": [term]})
        result = make_local(client).extract_structured("prompt", LLMFinancialResponse)
        assert isinstance(result, LLMFinancialResponse)
        (parsed,) = result.financial_terms
        assert (parsed.currency, parsed.description, parsed.conditions) == ("USD", "", [])
        assert len(client.calls) == 1


# ---------------------------------------------------------------------------
# LangChainProvider
# ---------------------------------------------------------------------------


class _FakeChatModel:
    """Like a LangChain model: temperature is an attribute read at call time."""

    def __init__(self, temperature: float = 0.0, fail: bool = False) -> None:
        self.temperature = temperature
        self.fail = fail
        self.seen: list[float] = []  # shared with copies, like a model's client

    def invoke(self, prompt: str, **kwargs: Any) -> str:
        self.seen.append(self.temperature)
        if self.fail:
            raise RuntimeError("rate limited")
        return "ok"


class _PydanticChatModel(BaseModel):
    """LangChain models are pydantic models; copying one must work too."""

    temperature: float = 0.0
    seen: list[float] = []

    def invoke(self, prompt: str, **kwargs: Any) -> SimpleNamespace:
        self.seen.append(self.temperature)
        return SimpleNamespace(content="ok")


class TestLangChainTemperature:
    def test_call_uses_requested_temperature_without_touching_the_shared_model(self):
        llm = _FakeChatModel(temperature=0.0)
        assert LangChainProvider(llm).complete("prompt", temperature=0.9) == "ok"
        assert llm.seen == [0.9]
        assert llm.temperature == 0.0

    def test_failed_call_leaves_the_shared_model_unchanged(self):
        llm = _FakeChatModel(temperature=0.0, fail=True)
        with pytest.raises(LLMProviderError, match="rate limited"):
            LangChainProvider(llm).complete("prompt", temperature=0.9)
        assert llm.seen == [0.9]
        assert llm.temperature == 0.0

    def test_shared_model_is_never_assigned_to(self):
        """No window in which a concurrent call could read another call's temperature."""

        class Frozen(_FakeChatModel):
            locked = False

            def __setattr__(self, name: str, value: Any) -> None:
                if name == "temperature" and self.locked:
                    raise AssertionError("temperature assigned on the shared model")
                super().__setattr__(name, value)

            def __copy__(self) -> _FakeChatModel:
                clone = _FakeChatModel(self.temperature)
                clone.seen = self.seen
                return clone

        llm = Frozen(temperature=0.2)
        llm.locked = True
        provider = LangChainProvider(llm)
        provider.complete("a", temperature=0.9)
        provider.complete("b", temperature=0.1)
        assert llm.seen == [0.9, 0.1]

    def test_pydantic_model_is_copied_too(self):
        llm = _PydanticChatModel()
        assert LangChainProvider(llm).complete("prompt", temperature=0.4) == "ok"
        assert llm.seen == [0.4]
        assert llm.temperature == 0.0

    def test_model_without_a_temperature_attribute_still_works(self):
        class Bare:
            def invoke(self, prompt: str, **kwargs: Any) -> str:
                return "ok"

        assert LangChainProvider(Bare()).complete("prompt", temperature=0.9) == "ok"
