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
        self._analyzer: Any | None = None

    def _get_analyzer(self) -> Any:
        if self._analyzer is None:
            from contractex.core.analyzers import RiskAnalyzer

            kwargs: dict[str, Any] = {}
            if isinstance(self._llm_provider, str):
                kwargs["llm_provider_name"] = self._llm_provider
            elif self._llm_provider is not None:
                kwargs["llm_provider"] = self._llm_provider

            self._analyzer = RiskAnalyzer(**kwargs)
        return self._analyzer

    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        if not doc.full_text:
            return doc

        analyzer = self._get_analyzer()
        risks = analyzer.analyze(doc.full_text)

        doc = doc.model_copy(update={
            "extracted": {**doc.extracted, "risks": risks},
        })
        return doc


# Self-register
TaskRegistry.default().register(RiskAnalysisTask)
