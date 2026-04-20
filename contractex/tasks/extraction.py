"""Contract extraction task — wraps ContractExtractor as a pipeline stage."""

from __future__ import annotations

from typing import Any

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry


class ContractExtractionTask(LegalTask):
    """
    Extract structured contract data (parties, clauses, financial terms) and
    merge results into ``doc.extracted``.

    Parameters
    ----------
    llm_provider:
        LLM provider instance or name string (e.g. ``"gpt-4o"``).
    confidence_threshold:
        Minimum confidence for accepted extractions.
    analyze_risks:
        Whether to run risk analysis as part of extraction.
    extract_financial:
        Whether to extract financial terms.
    """

    task_id = "contract_extraction"
    doc_types = [DocType.CONTRACT]
    requires_llm = True

    def __init__(
        self,
        llm_provider: Any | None = None,
        confidence_threshold: float = 0.7,
        analyze_risks: bool = True,
        extract_financial: bool = True,
    ) -> None:
        self._llm_provider = llm_provider
        self._confidence_threshold = confidence_threshold
        self._analyze_risks = analyze_risks
        self._extract_financial = extract_financial
        self._extractor: Any | None = None

    def _get_extractor(self) -> Any:
        if self._extractor is None:
            from contractex.core.extractors import ContractExtractor

            kwargs: dict[str, Any] = {
                "confidence_threshold": self._confidence_threshold,
            }
            if isinstance(self._llm_provider, str):
                kwargs["llm_provider_name"] = self._llm_provider
            elif self._llm_provider is not None:
                kwargs["llm_provider"] = self._llm_provider

            self._extractor = ContractExtractor(**kwargs)
        return self._extractor

    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        if not doc.full_text:
            return doc

        extractor = self._get_extractor()
        contract = extractor.extract_from_text(
            doc.full_text,
            analyze_risks=self._analyze_risks,
            extract_financial=self._extract_financial,
        )

        # Merge typed contract fields into doc.extracted
        contract_dict = contract.model_dump(mode="python")
        doc = doc.model_copy(
            update={
                "extracted": {**doc.extracted, "contract": contract_dict},
            }
        )
        return doc

    def estimate_cost(self, doc: LegalDoc) -> float:
        if not doc.full_text:
            return 0.0
        try:
            extractor = self._get_extractor()
            est = extractor.estimate_extraction_cost_from_text(doc.full_text)
            return float(est.get("estimated_cost", 0.0))
        except Exception:
            return 0.0


# Self-register
TaskRegistry.default().register(ContractExtractionTask)
