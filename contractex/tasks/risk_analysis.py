"""Risk analysis task — wraps RiskAnalyzer as a pipeline stage."""

from __future__ import annotations

from typing import Any

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry


class RiskAnalysisTask(LegalTask):
    """
    Identify risk flags in contract text and write them to
    ``doc.extracted["risks"]``.

    Parameters
    ----------
    llm_provider:
        LLM provider instance or name string.
    severity_threshold:
        Minimum severity level to include (``"low"``, ``"medium"``,
        ``"high"``, ``"critical"``).
    """

    task_id = "risk_analysis"
    doc_types = [DocType.CONTRACT]
    requires_llm = True

    def __init__(
        self,
        llm_provider: Any | None = None,
        severity_threshold: str = "low",
    ) -> None:
        self._llm_provider = llm_provider
        self._severity_threshold = severity_threshold

    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        if not doc.full_text:
            return doc

        from contractex.core.analyzers import RiskAnalyzer
        from contractex.core.models import Contract

        # Reuse clauses from a preceding contract_extraction task when present,
        # so the keyword rules have clauses to run over.
        contract = Contract.model_validate(
            doc.extracted.get("contract") or {"full_text": doc.full_text}
        )
        risks = RiskAnalyzer(llm_provider=self.llm_for(doc)).analyze(contract)

        doc = doc.model_copy(
            update={
                "extracted": {**doc.extracted, "risks": risks},
            }
        )
        return doc


# Self-register
TaskRegistry.default().register(RiskAnalysisTask)
