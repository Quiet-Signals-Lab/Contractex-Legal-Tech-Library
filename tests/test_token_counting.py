"""
Token counting and cost estimates are part of the privacy boundary: no built-in
path may hand document text to a provider's ``count_tokens`` or
``estimate_cost`` that it would not hand to ``complete``.
"""

from __future__ import annotations

import pytest

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.llm.anthropic_provider import AnthropicProvider
from contractex.privacy import PIIDetector, PrivacyAwareLLMRouter, PrivacyProfile
from contractex.tasks import TaskRegistry
from tests._providers import SpyLocalProvider, SpyProvider

TEXT = "Board minutes. Reach Jan on 415-555-0132 or jan@example.com."


class _CountingSpy(SpyProvider):
    """Records what is passed to the counting methods as well as to prompts."""

    def __init__(self) -> None:
        super().__init__()
        self.counted: list[str] = []

    def count_tokens(self, text: str) -> int:
        self.counted.append(text)
        return len(text) // 4

    def estimate_cost(self, text: str) -> float:
        self.counted.append(text)
        return 0.01


class _CountingLocalSpy(_CountingSpy, SpyLocalProvider):
    pass


def _doc(sensitivity: str) -> LegalDoc:
    return LegalDoc(
        doc_type=DocType.CONTRACT,
        full_text=TEXT,
        privacy_profile=PrivacyProfile(sensitivity=sensitivity),
    )


@pytest.fixture
def router() -> PrivacyAwareLLMRouter:
    return PrivacyAwareLLMRouter(detector=PIIDetector(use_presidio=False))


class _RecordingClient:
    """Stands in for ``anthropic.Anthropic``: records every token-count request."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.messages = self

    def count_tokens(self, **request):
        self.requests.append(request)
        return type("Response", (), {"input_tokens": 7})()


def test_anthropic_count_tokens_makes_no_api_call():
    provider = AnthropicProvider.__new__(AnthropicProvider)
    provider._model = "claude-3-5-sonnet-20241022"
    provider.client = _RecordingClient()
    assert provider.count_tokens("a" * 400) == 100
    assert provider.estimate_cost("a" * 400) > 0
    assert provider.client.requests == []


@pytest.mark.parametrize("sensitivity", ["confidential", "restricted"])
def test_guard_redacts_text_before_counting(router, sensitivity):
    spy = _CountingLocalSpy()
    guarded = router.guard(spy, _doc(sensitivity))
    guarded.count_tokens(TEXT)
    guarded.estimate_cost(TEXT)
    assert len(spy.counted) == 2
    assert not any("415-555-0132" in t or "jan@example.com" in t for t in spy.counted)


def test_guard_counts_public_text_unchanged(router):
    spy = _CountingSpy()
    router.guard(spy, _doc("public")).count_tokens(TEXT)
    assert spy.counted == [TEXT]


@pytest.mark.parametrize("sensitivity", ["secret", "restricted"])
def test_cost_estimate_gives_a_cloud_provider_nothing_it_may_not_see(sensitivity):
    spy = _CountingSpy()
    pipeline = TaskRegistry.default().build_pipeline(
        ["contract_extraction"], task_kwargs={"contract_extraction": {"llm_provider": spy}}
    )
    assert pipeline.estimate_total_cost(_doc(sensitivity)) == 0.0
    assert spy.counted == []
    assert spy.prompts == []


def test_cost_estimate_of_confidential_document_is_redacted():
    spy = _CountingSpy()
    pipeline = TaskRegistry.default().build_pipeline(
        ["contract_extraction"], task_kwargs={"contract_extraction": {"llm_provider": spy}}
    )
    assert pipeline.estimate_total_cost(_doc("confidential")) > 0
    assert spy.counted
    assert not any("415-555-0132" in t or "jan@example.com" in t for t in spy.counted)
