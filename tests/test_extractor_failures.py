"""
ContractExtractor must not turn a failed model call into "nothing found":
failures are recorded in ``Contract.metadata.warnings`` and a run in which
every call failed raises ``ExtractionError``.  Also covers the provider name
recorded in the metadata, model-name routing and amount parsing.

No network: every provider is a stub.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import BaseModel

from contractex.core.extraction_schemas import (
    LLMClauseResult,
    LLMClausesResponse,
    LLMContractInfoResponse,
    LLMFinancialResponse,
    LLMFinancialResult,
    LLMFullExtractionResponse,
    LLMPartyResult,
    LLMRiskResponse,
)
from contractex.core.extractors import ContractExtractor
from contractex.exceptions import ExtractionError
from contractex.privacy import PrivacyAwareLLMRouter
from tests._providers import SpyProvider

TEXT = "8. Termination. Either party may terminate this Agreement on 30 days notice."
INFO = LLMContractInfoResponse(parties=[LLMPartyResult(name="Acme Corp", confidence=0.9)])
CLAUSES = LLMClausesResponse(
    clauses=[LLMClauseResult(clause_type="termination_for_convenience", text=TEXT, confidence=0.9)]
)


class ScriptedProvider(SpyProvider):
    """Raises for the schemas in *failing*; returns *replies* or an empty schema otherwise."""

    def __init__(
        self,
        failing: tuple[type[BaseModel], ...] = (),
        replies: dict[type[BaseModel], BaseModel] | None = None,
        fail_first: int = 0,
    ) -> None:
        super().__init__()
        self.failing = failing
        self.replies = replies or {}
        self.fail_first = fail_first  # fail this many calls for a failing schema, then recover
        self.failed = 0

    def extract_structured(self, prompt, schema, temperature=0.0, max_tokens=None):
        self.prompts.append(prompt)
        if schema in self.failing and (not self.fail_first or self.failed < self.fail_first):
            self.failed += 1
            raise RuntimeError("401 invalid x-api-key\nrequest body: " + prompt)
        return self.replies.get(schema, schema())


EVERY_SCHEMA = (
    LLMContractInfoResponse,
    LLMFullExtractionResponse,
    LLMClausesResponse,
    LLMFinancialResponse,
    LLMRiskResponse,
)


def two_chunks() -> list[str]:
    return ["1. First. Chunk one text.", "2. Second. Chunk two text."]


# ---------------------------------------------------------------------------
# Total failure
# ---------------------------------------------------------------------------


class TestEveryCallFails:
    def test_single_chunk_raises_instead_of_returning_an_empty_contract(self):
        extractor = ContractExtractor(llm_provider=ScriptedProvider(failing=EVERY_SCHEMA))
        with pytest.raises(ExtractionError, match="401 invalid x-api-key"):
            extractor.extract_from_text(TEXT)

    @pytest.mark.parametrize("parallel", [True, False])
    def test_multi_chunk_raises(self, parallel):
        extractor = ContractExtractor(
            llm_provider=ScriptedProvider(failing=EVERY_SCHEMA), parallel_processing=parallel
        )
        with pytest.raises(ExtractionError, match="LLM calls failed"):
            extractor._extract_from_chunks(two_chunks())

    def test_raises_without_financial_extraction_too(self):
        extractor = ContractExtractor(llm_provider=ScriptedProvider(failing=EVERY_SCHEMA))
        with pytest.raises(ExtractionError):
            extractor.extract_from_text(TEXT, extract_financial=False, analyze_risks=False)

    def test_error_does_not_echo_the_prompt(self):
        extractor = ContractExtractor(llm_provider=ScriptedProvider(failing=EVERY_SCHEMA))
        with pytest.raises(ExtractionError) as excinfo:
            extractor.extract_from_text(TEXT)
        assert "request body" not in str(excinfo.value)


# ---------------------------------------------------------------------------
# Partial failure
# ---------------------------------------------------------------------------


class TestPartialFailureIsRecorded:
    def test_contract_info_failure_is_a_warning(self):
        llm = ScriptedProvider(
            failing=(LLMContractInfoResponse,),
            replies={LLMFullExtractionResponse: LLMFullExtractionResponse(clauses=CLAUSES.clauses)},
        )
        contract = ContractExtractor(llm_provider=llm).extract_from_text(TEXT, analyze_risks=False)
        assert len(contract.clauses) == 1 and contract.parties == []
        (warning,) = contract.metadata.warnings
        assert "Contract info extraction failed" in warning and "401" in warning
        assert "request body" not in warning  # first line of the error only

    def test_single_chunk_fallback_failures_are_warnings(self):
        llm = ScriptedProvider(
            failing=(LLMFullExtractionResponse, LLMClausesResponse, LLMFinancialResponse),
            replies={LLMContractInfoResponse: INFO},
        )
        contract = ContractExtractor(llm_provider=llm).extract_from_text(TEXT, analyze_risks=False)
        assert [p.name for p in contract.parties] == ["Acme Corp"]
        warnings = contract.metadata.warnings
        assert any("Clause extraction failed" in w for w in warnings)
        assert any("Financial extraction failed" in w for w in warnings)

    def test_combined_call_recovered_by_fallback_is_not_a_warning(self):
        llm = ScriptedProvider(
            failing=(LLMFullExtractionResponse,),
            replies={LLMContractInfoResponse: INFO, LLMClausesResponse: CLAUSES},
        )
        contract = ContractExtractor(llm_provider=llm).extract_from_text(TEXT, analyze_risks=False)
        assert len(contract.clauses) == 1
        assert contract.metadata.warnings == []

    def test_failed_chunk_is_named_in_the_warnings(self):
        llm = ScriptedProvider(
            failing=(LLMClausesResponse,),
            fail_first=1,
            replies={LLMContractInfoResponse: INFO, LLMClausesResponse: CLAUSES},
        )
        extractor = ContractExtractor(llm_provider=llm, parallel_processing=False)
        result = extractor._extract_from_chunks(two_chunks(), extract_financial=False)
        assert len(result["clauses"]) == 1
        (warning,) = result["_metadata"]["warnings"]
        assert warning.startswith("Chunk 0: Clause extraction failed")

    def test_risk_analysis_failure_is_a_warning(self):
        llm = ScriptedProvider(
            failing=(LLMRiskResponse,),
            replies={
                LLMContractInfoResponse: INFO,
                LLMFullExtractionResponse: LLMFullExtractionResponse(clauses=CLAUSES.clauses),
            },
        )
        contract = ContractExtractor(llm_provider=llm).extract_from_text(TEXT)
        assert contract.risks == []
        assert any("LLM risk analysis failed" in w for w in contract.metadata.warnings)

    def test_success_has_no_warnings(self):
        llm = ScriptedProvider(
            replies={
                LLMContractInfoResponse: INFO,
                LLMFullExtractionResponse: LLMFullExtractionResponse(clauses=CLAUSES.clauses),
            }
        )
        contract = ContractExtractor(llm_provider=llm).extract_from_text(TEXT)
        assert contract.metadata.warnings == []

    def test_multi_chunk_clause_order_follows_chunk_order(self):
        class EchoChunk(ScriptedProvider):
            def extract_structured(self, prompt, schema, temperature=0.0, max_tokens=None):
                if schema is LLMClausesResponse:
                    marker = "one" if "Chunk one" in prompt else "two"
                    return LLMClausesResponse(
                        clauses=[
                            LLMClauseResult(
                                clause_type=f"type_{marker}",
                                text=f"Clause {marker}",
                                confidence=0.9,
                            )
                        ]
                    )
                return schema()

        extractor = ContractExtractor(llm_provider=EchoChunk())
        for _ in range(5):
            result = extractor._extract_from_chunks(two_chunks(), extract_financial=False)
            assert [c.clause_type for c in result["clauses"]] == ["type_one", "type_two"]


# ---------------------------------------------------------------------------
# Provider name in the metadata
# ---------------------------------------------------------------------------


class TestProviderName:
    def test_guarded_provider_is_recorded_by_its_own_class_name(self):
        guarded = PrivacyAwareLLMRouter().guard(SpyProvider())
        extractor = ContractExtractor(llm_provider=guarded)
        contract = extractor.extract_from_text(TEXT, analyze_risks=False)
        assert contract.metadata.llm_provider == "SpyProvider"
        assert extractor.estimate_extraction_cost_from_text(TEXT)["llm_provider"] == "SpyProvider"

    def test_plain_provider_name_unchanged(self):
        contract = ContractExtractor(llm_provider=SpyProvider()).extract_from_text(
            TEXT, analyze_risks=False
        )
        assert contract.metadata.llm_provider == "SpyProvider"


# ---------------------------------------------------------------------------
# Model-name routing
# ---------------------------------------------------------------------------


@pytest.fixture
def offline_providers(monkeypatch):
    from contractex.llm import AnthropicProvider, LocalProvider, OpenAIProvider

    def init(self, model: str, *args, **kwargs) -> None:
        self._model = model

    for cls in (LocalProvider, OpenAIProvider, AnthropicProvider):
        monkeypatch.setattr(cls, "__init__", init)


class TestCreateProvider:
    @pytest.mark.parametrize("name", ["gpt-oss:20b", "gpt-oss:120b", "GPT-OSS", "gpt-oss"])
    def test_gpt_oss_is_an_ollama_model(self, offline_providers, name):
        provider = ContractExtractor._create_provider(name)
        assert type(provider).__name__ == "LocalProvider"
        assert provider.model == name

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("gpt-4o-mini", "OpenAIProvider"),
            ("claude-sonnet-4", "AnthropicProvider"),
            ("llama3.1:8b", "LocalProvider"),
        ],
    )
    def test_other_names_route_as_before(self, offline_providers, name, expected):
        assert type(ContractExtractor._create_provider(name)).__name__ == expected

    @pytest.mark.parametrize("name", ["openai", "gpt", "chatgpt-latest", "Claude"])
    def test_vendor_names_still_rejected(self, offline_providers, name):
        with pytest.raises(ValueError, match="does not name a model"):
            ContractExtractor._create_provider(name)


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------


class TestPlainNumericAmounts:
    def _build(self, amount: str):
        extractor = ContractExtractor(llm_provider=SpyProvider())
        (term,) = extractor._build_financial_terms(
            [LLMFinancialResult(term_type="service_fee", amount=amount, confidence=0.9)]
        )
        return term

    @pytest.mark.parametrize("amount", ["50000.00", "1500", "0.015", "-250.00", " 42 ", "1.500"])
    def test_plain_numeric_string_is_parsed_exactly_without_the_normaliser(
        self, monkeypatch, amount
    ):
        from contractex.utils.normalizers import CurrencyNormalizer

        def unexpected(text: str):
            raise AssertionError(f"normaliser called for plain number {text!r}")

        monkeypatch.setattr(CurrencyNormalizer, "extract_amount", staticmethod(unexpected))
        assert self._build(amount).amount == Decimal(amount.strip())

    @pytest.mark.parametrize("amount", ["$50,000", "USD 1,500.00", "NaN", "1e5", "Infinity"])
    def test_anything_else_goes_to_the_normaliser(self, monkeypatch, amount):
        from contractex.utils.normalizers import CurrencyNormalizer

        seen: list[str] = []

        def record(text: str):
            seen.append(text)
            return Decimal("7")

        monkeypatch.setattr(CurrencyNormalizer, "extract_amount", staticmethod(record))
        assert self._build(amount).amount == Decimal("7")
        assert seen == [amount]

    @pytest.mark.parametrize("amount", ["variable", "NaN", "Infinity"])
    def test_amount_the_normaliser_rejects_is_none(self, monkeypatch, amount):
        from contractex.utils.normalizers import CurrencyNormalizer

        monkeypatch.setattr(CurrencyNormalizer, "extract_amount", staticmethod(lambda text: None))
        assert self._build(amount).amount is None
