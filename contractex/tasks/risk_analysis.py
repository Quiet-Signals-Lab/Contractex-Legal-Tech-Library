"""Risk analysis task — wraps LLMRiskAnalyzer as a pipeline stage."""

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

    The keyword rules always run.  If the model call fails, their results are
    still returned and the failure is listed in
    ``doc.extracted["risk_warnings"]`` (empty when the model answered).

    After a ``contract_extraction`` task that already analysed risks, those
    results are reused and the model is not asked again.

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

        from contractex.core.analyzers import RISK_FAILURE, LLMRiskAnalyzer
        from contractex.core.models import Contract

        # Reuse clauses from a preceding contract_extraction task when present,
        # so the keyword rules have clauses to run over.
        contract = Contract.model_validate(
            doc.extracted.get("contract") or {"full_text": doc.full_text}
        )
        # prompt_versions names the prompts an extraction sent
        if "risk_analysis" in contract.metadata.prompt_versions:
            risks = contract.risks
        else:
            risks = LLMRiskAnalyzer(llm_provider=self.llm_for(doc)).analyze(contract)
        warnings = [w for w in contract.metadata.warnings if w.startswith(RISK_FAILURE)]

        doc = doc.model_copy(
            update={
                "extracted": {**doc.extracted, "risks": risks, "risk_warnings": warnings},
            }
        )
        return doc


# Self-register
TaskRegistry.default().register(RiskAnalysisTask)
