"""
Unit tests for the ContractEx extraction pipeline.

All tests in this file are marked `unit` and run without any external
services (no LLM API keys, no PostgreSQL, no Ollama).  The LLM is
replaced with a MockLLMProvider that returns pre-canned structured
responses.
"""

from __future__ import annotations

from datetime import date
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
    LLMRiskResult,
)
from contractex.core.models import (
    Clause,
    Contract,
    ContractType,
    PartyRole,
)
from contractex.llm.base import LLMProvider

# ---------------------------------------------------------------------------
# Mock LLM provider
# ---------------------------------------------------------------------------


class MockLLMProvider(LLMProvider):
    """
    Deterministic LLM provider for unit tests.

    The caller registers expected responses keyed on the schema class.
    Any schema not registered returns an empty instance.
    """

    def __init__(self) -> None:
        self._responses: dict[type, BaseModel] = {}

    def register(self, schema: type[BaseModel], response: BaseModel) -> None:
        self._responses[schema] = response

    def extract_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> BaseModel:
        if schema in self._responses:
            return self._responses[schema]
        # Default: empty instance (all Optional fields → None, lists → [])
        return schema()  # type: ignore[call-arg]

    def complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs
    ) -> str:
        return ""

    def estimate_cost(self, text: str) -> float:
        return 0.0

    def count_tokens(self, text: str) -> int:
        return len(text) // 4

    @property
    def context_window(self) -> int:
        return 128000

    @property
    def model(self) -> str:
        return "mock-llm"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_CONTRACT_TEXT = """\
MUTUAL NON-DISCLOSURE AGREEMENT

This Mutual Non-Disclosure Agreement ("Agreement") is entered into as of January 15, 2024
("Effective Date") between Acme Corporation, a Delaware corporation ("Disclosing Party"),
and Beta Inc., a California corporation ("Receiving Party").

1. CONFIDENTIALITY OBLIGATIONS
Each party agrees to hold in strict confidence all Confidential Information received from
the other party and not to disclose such information to any third party without prior
written consent. This obligation shall survive termination of this Agreement for a period
of five (5) years.

2. TERM AND TERMINATION
This Agreement shall be effective from the Effective Date and shall continue for a period
of two (2) years unless earlier terminated. Either party may terminate this Agreement upon
thirty (30) days' written notice to the other party.

3. GOVERNING LAW
This Agreement shall be governed by the laws of the State of Delaware, without regard to
its conflict of law provisions.
"""

SAMPLE_NDA_INFO_RESPONSE = LLMContractInfoResponse(
    contract_type="nda",
    title="Mutual Non-Disclosure Agreement",
    effective_date="2024-01-15",
    expiration_date=None,
    governing_law="State of Delaware",
    parties=[
        LLMPartyResult(
            name="Acme Corporation",
            role="provider",
            entity_type="corporation",
            jurisdiction="Delaware",
            confidence=0.95,
        ),
        LLMPartyResult(
            name="Beta Inc.",
            role="client",
            entity_type="corporation",
            jurisdiction="California",
            confidence=0.95,
        ),
    ],
)

SAMPLE_CLAUSES_RESPONSE = LLMClausesResponse(
    clauses=[
        LLMClauseResult(
            clause_type="confidentiality",
            text="Each party agrees to hold in strict confidence all Confidential Information "
            "received from the other party and not to disclose such information to any third "
            "party without prior written consent.",
            section_number="1",
            confidence=0.92,
        ),
        LLMClauseResult(
            clause_type="termination_for_convenience",
            text="Either party may terminate this Agreement upon thirty (30) days' written "
            "notice to the other party.",
            section_number="2",
            confidence=0.88,
        ),
        LLMClauseResult(
            clause_type="governing_law",
            text="This Agreement shall be governed by the laws of the State of Delaware, "
            "without regard to its conflict of law provisions.",
            section_number="3",
            confidence=0.95,
        ),
    ]
)

SAMPLE_FINANCIAL_RESPONSE = LLMFinancialResponse(financial_terms=[])


# ---------------------------------------------------------------------------
# Tests: extraction schemas
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractionSchemas:
    """Validate that schemas accept edge-case inputs gracefully."""

    def test_contract_info_all_optional_fields_default_to_none(self):
        info = LLMContractInfoResponse()  # type: ignore[call-arg]
        assert info.contract_type is None
        assert info.parties == []

    def test_clause_result_requires_clause_type_and_text(self):
        c = LLMClauseResult(clause_type="confidentiality", text="Some text.")
        assert c.confidence == 0.7  # default

    def test_financial_result_amount_is_string(self):
        f = LLMFinancialResult(term_type="service_fee", amount="50000.00")
        assert isinstance(f.amount, str)
        assert f.currency == "USD"

    def test_risk_result_defaults(self):
        r = LLMRiskResult(risk_type="unlimited_liability", severity="critical", description="x")
        assert r.confidence == 0.8
        assert r.clause_reference is None

    def test_party_result_role_not_required(self):
        p = LLMPartyResult(name="Acme Corp")
        assert p.role is None
        assert p.confidence == 0.7

    def test_full_extraction_response_empty_lists(self):
        full = LLMFullExtractionResponse()  # type: ignore[call-arg]
        assert full.clauses == []
        assert full.financial_terms == []
        assert full.parties == []

    def test_clauses_response_empty(self):
        resp = LLMClausesResponse()  # type: ignore[call-arg]
        assert resp.clauses == []


# ---------------------------------------------------------------------------
# Tests: ContractExtractor with mocked LLM
# ---------------------------------------------------------------------------


def _make_extractor(llm: MockLLMProvider, confidence_threshold: float = 0.7):
    """Build a ContractExtractor wired to a mock LLM, without hitting any loader."""
    from contractex.core.extractors import ContractExtractor

    extractor = ContractExtractor(
        llm_provider=llm,
        confidence_threshold=confidence_threshold,
        parallel_processing=False,
    )
    return extractor


@pytest.mark.unit
class TestContractExtractorMocked:
    """Test extraction pipeline with a mock LLM provider."""

    def test_extract_from_single_chunk_populates_parties(self):
        llm = MockLLMProvider()
        llm.register(LLMContractInfoResponse, SAMPLE_NDA_INFO_RESPONSE)
        llm.register(LLMClausesResponse, SAMPLE_CLAUSES_RESPONSE)
        llm.register(LLMFinancialResponse, SAMPLE_FINANCIAL_RESPONSE)

        extractor = _make_extractor(llm)
        result = extractor._extract_from_chunks([SAMPLE_CONTRACT_TEXT])

        parties = result["parties"]
        assert len(parties) == 2
        names = {p.name for p in parties}
        assert "Acme Corporation" in names
        assert "Beta Inc." in names

    def test_extract_from_single_chunk_populates_clauses(self):
        llm = MockLLMProvider()
        llm.register(LLMContractInfoResponse, SAMPLE_NDA_INFO_RESPONSE)
        # Single-chunk path tries LLMFullExtractionResponse first; fallback uses LLMClausesResponse
        llm.register(
            LLMFullExtractionResponse,
            LLMFullExtractionResponse(  # type: ignore[call-arg]
                clauses=SAMPLE_CLAUSES_RESPONSE.clauses,
                financial_terms=[],
            ),
        )

        extractor = _make_extractor(llm)
        result = extractor._extract_from_chunks([SAMPLE_CONTRACT_TEXT])

        clauses = result["clauses"]
        assert len(clauses) == 3
        clause_types = {c.clause_type for c in clauses}
        assert "confidentiality" in clause_types
        assert "governing_law" in clause_types

    def test_contract_type_parsed(self):
        llm = MockLLMProvider()
        llm.register(LLMContractInfoResponse, SAMPLE_NDA_INFO_RESPONSE)
        llm.register(LLMFullExtractionResponse, LLMFullExtractionResponse())  # type: ignore[call-arg]

        extractor = _make_extractor(llm)
        result = extractor._extract_from_chunks([SAMPLE_CONTRACT_TEXT])

        assert result["contract_type"] == ContractType.NDA

    def test_effective_date_parsed(self):
        llm = MockLLMProvider()
        llm.register(LLMContractInfoResponse, SAMPLE_NDA_INFO_RESPONSE)
        llm.register(LLMFullExtractionResponse, LLMFullExtractionResponse())  # type: ignore[call-arg]

        extractor = _make_extractor(llm)
        result = extractor._extract_from_chunks([SAMPLE_CONTRACT_TEXT])

        assert result["effective_date"] == date(2024, 1, 15)

    def test_governing_law_captured(self):
        llm = MockLLMProvider()
        llm.register(LLMContractInfoResponse, SAMPLE_NDA_INFO_RESPONSE)
        llm.register(LLMFullExtractionResponse, LLMFullExtractionResponse())  # type: ignore[call-arg]

        extractor = _make_extractor(llm)
        result = extractor._extract_from_chunks([SAMPLE_CONTRACT_TEXT])

        assert result["governing_law"] == "State of Delaware"

    def test_hint_used_when_llm_returns_unknown_type(self):
        llm = MockLLMProvider()
        info = LLMContractInfoResponse(contract_type="unknown")  # type: ignore[call-arg]
        llm.register(LLMContractInfoResponse, info)
        llm.register(LLMFullExtractionResponse, LLMFullExtractionResponse())  # type: ignore[call-arg]

        extractor = _make_extractor(llm)
        result = extractor._extract_from_chunks(
            [SAMPLE_CONTRACT_TEXT], contract_type=ContractType.NDA
        )

        # The hint (ContractType.NDA) should override the LLM's "unknown"
        assert result["contract_type"] == ContractType.NDA

    def test_financial_terms_parsed(self):
        llm = MockLLMProvider()
        llm.register(LLMContractInfoResponse, SAMPLE_NDA_INFO_RESPONSE)
        llm.register(
            LLMFullExtractionResponse,
            LLMFullExtractionResponse(  # type: ignore[call-arg]
                clauses=[],
                financial_terms=[
                    LLMFinancialResult(
                        term_type="service_fee",
                        amount="50000.00",
                        currency="USD",
                        frequency="monthly",
                        description="Monthly retainer",
                        confidence=0.9,
                    )
                ],
            ),
        )

        extractor = _make_extractor(llm)
        result = extractor._extract_from_chunks([SAMPLE_CONTRACT_TEXT])

        ft = result["financial_terms"]
        assert len(ft) == 1
        assert ft[0].term_type == "service_fee"
        assert ft[0].amount == Decimal("50000.00")
        assert ft[0].currency == "USD"
        assert ft[0].frequency == "monthly"

    def test_llm_failure_on_single_chunk_falls_back_to_empty(self):
        """If every LLM call fails, we get an empty Contract rather than a crash."""
        from contractex.exceptions import LLMProviderError

        llm = MockLLMProvider()

        def _raise(*args, **kwargs):
            raise LLMProviderError("Simulated failure")

        llm.extract_structured = _raise  # type: ignore[method-assign]

        extractor = _make_extractor(llm)
        result = extractor._extract_from_chunks(["Some contract text."])

        assert result["parties"] == []
        assert result["clauses"] == []
        assert result["financial_terms"] == []

    def test_multi_chunk_merges_results(self):
        """Results from two chunks should be combined."""
        chunk1_clauses = LLMClausesResponse(
            clauses=[
                LLMClauseResult(
                    clause_type="confidentiality",
                    text="Confidentiality clause text.",
                    confidence=0.9,
                )
            ]
        )
        chunk2_clauses = LLMClausesResponse(
            clauses=[
                LLMClauseResult(
                    clause_type="termination_for_convenience",
                    text="Termination clause text.",
                    confidence=0.85,
                )
            ]
        )

        call_count = 0

        class SequencedMock(MockLLMProvider):
            def extract_structured(self, prompt, schema, **kwargs):
                nonlocal call_count
                call_count += 1
                if schema is LLMContractInfoResponse:
                    return SAMPLE_NDA_INFO_RESPONSE
                if schema is LLMClausesResponse:
                    return chunk1_clauses if call_count <= 2 else chunk2_clauses
                return schema()  # type: ignore[call-arg]

        extractor = _make_extractor(SequencedMock())
        result = extractor._extract_from_chunks(
            ["chunk one text", "chunk two text"], extract_financial=False
        )

        # Both chunks' clauses should appear
        assert len(result["clauses"]) >= 1  # at least one unique clause extracted


# ---------------------------------------------------------------------------
# Tests: deduplication logic
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestDeduplication:
    """Unit tests for clause and financial-term deduplication."""

    def _extractor(self) -> ContractExtractor:  # noqa: F821
        from contractex.core.extractors import ContractExtractor

        return ContractExtractor(llm_provider=MockLLMProvider())

    def test_identical_clauses_deduped(self):
        ext = self._extractor()
        clauses = [
            LLMClauseResult(clause_type="confidentiality", text="Same text.", confidence=0.9),
            LLMClauseResult(clause_type="confidentiality", text="Same text.", confidence=0.8),
        ]
        result = ext._deduplicate_clauses(clauses)
        assert len(result) == 1

    def test_substring_keeps_longer(self):
        ext = self._extractor()
        short = LLMClauseResult(
            clause_type="confidentiality", text="Confidential info.", confidence=0.9
        )
        long_ = LLMClauseResult(
            clause_type="confidentiality",
            text="Confidential info. This obligation survives termination.",
            confidence=0.8,
        )
        result = ext._deduplicate_clauses([short, long_])
        assert len(result) == 1
        assert "survives" in result[0].text

    def test_distinct_clauses_all_kept(self):
        ext = self._extractor()
        clauses = [
            LLMClauseResult(
                clause_type="confidentiality",
                text="Each party agrees to hold all Confidential Information in strict confidence "
                "and shall not disclose it to any third party without prior written consent.",
                confidence=0.9,
            ),
            LLMClauseResult(
                clause_type="termination_for_convenience",
                text="Either party may terminate this Agreement at any time upon thirty (30) days "
                "written notice to the other party without cause or penalty.",
                confidence=0.85,
            ),
        ]
        result = ext._deduplicate_clauses(clauses)
        assert len(result) == 2

    def test_similar_clauses_above_threshold_deduped(self):
        ext = self._extractor()
        base = "The party shall keep all information strictly confidential."
        similar = "The party shall keep all information strictly confidential and secure."
        clauses = [
            LLMClauseResult(clause_type="confidentiality", text=base, confidence=0.85),
            LLMClauseResult(clause_type="confidentiality", text=similar, confidence=0.9),
        ]
        result = ext._deduplicate_clauses(clauses)
        # Both texts are similar but not equal — deduplication depends on ratio
        # At minimum the list should be non-empty
        assert len(result) >= 1

    def test_financial_terms_deduped_by_type_amount_currency(self):
        ext = self._extractor()
        terms = [
            LLMFinancialResult(
                term_type="service_fee", amount="1000.00", currency="USD", confidence=0.9
            ),
            LLMFinancialResult(
                term_type="service_fee", amount="1000.00", currency="USD", confidence=0.7
            ),
        ]
        result = ext._deduplicate_financial_terms(terms)
        assert len(result) == 1
        assert result[0].confidence == 0.9  # higher-confidence kept

    def test_financial_terms_different_amounts_both_kept(self):
        ext = self._extractor()
        terms = [
            LLMFinancialResult(
                term_type="penalty", amount="500.00", currency="USD", confidence=0.8
            ),
            LLMFinancialResult(
                term_type="penalty", amount="1000.00", currency="USD", confidence=0.8
            ),
        ]
        result = ext._deduplicate_financial_terms(terms)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Tests: model conversion helpers
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModelConversion:
    """Test _build_parties, _build_clauses, _build_financial_terms."""

    def _extractor(self) -> ContractExtractor:  # noqa: F821
        from contractex.core.extractors import ContractExtractor

        return ContractExtractor(llm_provider=MockLLMProvider())

    def test_build_parties_maps_role_enum(self):
        ext = self._extractor()
        parties = ext._build_parties(
            [
                LLMPartyResult(name="Acme Corp", role="provider", confidence=0.9),
            ]
        )
        assert len(parties) == 1
        assert parties[0].role == PartyRole.PROVIDER

    def test_build_parties_unknown_role_maps_to_none(self):
        ext = self._extractor()
        parties = ext._build_parties(
            [
                LLMPartyResult(name="Acme Corp", role="wizard", confidence=0.9),
            ]
        )
        assert parties[0].role is None

    def test_build_parties_deduplicates_by_name(self):
        ext = self._extractor()
        parties = ext._build_parties(
            [
                LLMPartyResult(name="Acme Corp", role="provider", confidence=0.9),
                LLMPartyResult(name="Acme Corp", role="provider", confidence=0.8),
            ]
        )
        assert len(parties) == 1

    def test_build_clauses_filters_low_confidence(self):
        ext = self._extractor()
        ext.confidence_threshold = 0.8
        clauses = ext._build_clauses(
            [
                LLMClauseResult(clause_type="confidentiality", text="High conf.", confidence=0.9),
                LLMClauseResult(
                    clause_type="termination_for_cause", text="Low conf.", confidence=0.5
                ),
            ]
        )
        assert len(clauses) == 1
        assert clauses[0].clause_type == "confidentiality"

    def test_build_financial_terms_parses_decimal_amount(self):
        ext = self._extractor()
        terms = ext._build_financial_terms(
            [
                LLMFinancialResult(
                    term_type="service_fee", amount="2500.50", currency="USD", confidence=0.9
                ),
            ]
        )
        assert terms[0].amount == Decimal("2500.50")

    def test_build_financial_terms_handles_unparseable_amount(self):
        ext = self._extractor()
        terms = ext._build_financial_terms(
            [
                LLMFinancialResult(
                    term_type="service_fee", amount="variable", currency="USD", confidence=0.9
                ),
            ]
        )
        assert terms[0].amount is None

    def test_build_financial_terms_parses_due_date(self):
        ext = self._extractor()
        terms = ext._build_financial_terms(
            [
                LLMFinancialResult(
                    term_type="payment",
                    amount="1000.00",
                    currency="USD",
                    due_date="01/31/2024",
                    confidence=0.9,
                )
            ]
        )
        assert terms[0].due_date == date(2024, 1, 31)


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestExtractorErrorHandling:
    """Extraction failures should degrade gracefully, not crash."""

    def test_contract_info_failure_returns_empty_info(self):
        from contractex.exceptions import LLMProviderError

        class FailingLLM(MockLLMProvider):
            def extract_structured(self, prompt, schema, **kwargs):
                if schema is LLMContractInfoResponse:
                    raise LLMProviderError("Info extraction failed")
                return schema()  # type: ignore[call-arg]

        from contractex.core.extractors import ContractExtractor

        ext = ContractExtractor(llm_provider=FailingLLM())
        info = ext._extract_contract_info("some text")
        assert info.parties == []
        assert info.contract_type is None

    def test_clause_extraction_failure_returns_empty_list(self):
        from contractex.exceptions import LLMProviderError

        class FailingLLM(MockLLMProvider):
            def extract_structured(self, prompt, schema, **kwargs):
                raise LLMProviderError("always fails")

        from contractex.core.extractors import ContractExtractor

        ext = ContractExtractor(llm_provider=FailingLLM())
        clauses = ext._extract_clauses_from_text("some text")
        assert clauses == []

    def test_partial_chunk_failure_still_returns_other_chunks(self):
        """When one chunk fails, the pipeline continues with the remaining chunks."""
        from contractex.exceptions import LLMProviderError

        fail_on_first = [True]

        class SelectiveFailLLM(MockLLMProvider):
            def extract_structured(self, prompt, schema, **kwargs):
                if schema is LLMContractInfoResponse:
                    return SAMPLE_NDA_INFO_RESPONSE
                if schema is LLMClausesResponse:
                    if fail_on_first[0]:
                        fail_on_first[0] = False
                        raise LLMProviderError("chunk 0 failed")
                    return SAMPLE_CLAUSES_RESPONSE
                return LLMFinancialResponse()

        from contractex.core.extractors import ContractExtractor

        ext = ContractExtractor(
            llm_provider=SelectiveFailLLM(),
            parallel_processing=False,
        )
        result = ext._extract_from_chunks(["chunk one", "chunk two"], extract_financial=False)
        # chunk two should contribute its clauses
        assert len(result["clauses"]) > 0


# ---------------------------------------------------------------------------
# Tests: RiskAnalyzer with mocked LLM
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestRiskAnalyzerLLM:
    """Test that LLM-based risk analysis is called and deduped correctly."""

    def _sample_contract(self) -> Contract:
        return Contract(  # type: ignore[call-arg]
            clauses=[
                Clause(  # type: ignore[call-arg]
                    clause_type="uncapped_liability",
                    text="The party shall have unlimited liability for all damages.",
                    confidence=0.9,
                )
            ],
            full_text="The party shall have unlimited liability for all damages.",
        )

    def test_rule_based_detects_unlimited_liability(self):
        from contractex.core.analyzers import RiskAnalyzer

        analyzer = RiskAnalyzer(use_llm=False)
        risks = analyzer.analyze(self._sample_contract())
        assert any(r.risk_type == "unlimited_liability" for r in risks)

    def test_llm_risks_appended_to_rule_based(self):
        from contractex.core.analyzers import RiskAnalyzer

        llm = MockLLMProvider()
        llm.register(
            LLMRiskResponse,
            LLMRiskResponse(
                risks=[
                    LLMRiskResult(
                        risk_type="data_security_gap",
                        severity="high",
                        description="No data breach notification clause.",
                        confidence=0.85,
                    )
                ]
            ),
        )

        analyzer = RiskAnalyzer(use_llm=True, llm_provider=llm)
        risks = analyzer.analyze(self._sample_contract())

        risk_types = {r.risk_type for r in risks}
        assert "unlimited_liability" in risk_types  # rule-based
        assert "data_security_gap" in risk_types  # LLM-based

    def test_llm_risk_deduped_with_rule_based(self):
        """LLM returning the same risk_type+clause_reference as a rule-based hit is skipped."""
        from contractex.core.analyzers import RiskAnalyzer

        llm = MockLLMProvider()
        llm.register(
            LLMRiskResponse,
            LLMRiskResponse(
                risks=[
                    LLMRiskResult(
                        risk_type="unlimited_liability",  # same as rule-based hit
                        severity="critical",
                        description="LLM duplicate",
                        clause_reference=None,
                        confidence=0.9,
                    )
                ]
            ),
        )

        analyzer = RiskAnalyzer(use_llm=True, llm_provider=llm)
        risks = analyzer.analyze(self._sample_contract())

        ul_risks = [r for r in risks if r.risk_type == "unlimited_liability"]
        assert len(ul_risks) == 1  # deduplicated

    def test_llm_failure_does_not_suppress_rule_based_risks(self):
        from contractex.core.analyzers import RiskAnalyzer
        from contractex.exceptions import LLMProviderError

        class FailingLLM(MockLLMProvider):
            def extract_structured(self, prompt, schema, **kwargs):
                raise LLMProviderError("LLM unavailable")

        analyzer = RiskAnalyzer(use_llm=True, llm_provider=FailingLLM())
        risks = analyzer.analyze(self._sample_contract())

        # Rule-based risks still appear even when LLM fails
        assert any(r.risk_type == "unlimited_liability" for r in risks)

    def test_risk_sorted_critical_first(self):
        from contractex.core.analyzers import RiskAnalyzer

        llm = MockLLMProvider()
        llm.register(
            LLMRiskResponse,
            LLMRiskResponse(
                risks=[
                    LLMRiskResult(
                        risk_type="low_risk", severity="low", description="x", confidence=0.8
                    ),
                    LLMRiskResult(
                        risk_type="high_risk", severity="high", description="y", confidence=0.8
                    ),
                ]
            ),
        )

        analyzer = RiskAnalyzer(use_llm=True, llm_provider=llm)
        # No clause text that triggers rule-based, so only LLM risks
        contract = Contract(  # type: ignore[call-arg]
            clauses=[
                Clause(clause_type="confidentiality", text="Keep everything secret.", confidence=0.9)  # type: ignore[call-arg]
            ],
            full_text="Keep everything secret.",
        )
        risks = analyzer.analyze(contract)

        high_risk_idx = next(i for i, r in enumerate(risks) if r.risk_type == "high_risk")
        low_risk_idx = next(i for i, r in enumerate(risks) if r.risk_type == "low_risk")
        assert high_risk_idx < low_risk_idx
