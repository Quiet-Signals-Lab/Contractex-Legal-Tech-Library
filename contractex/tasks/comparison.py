"""Comparison task — compare two legal documents and surface differences."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry


class DocumentDiff(BaseModel):
    """A single substantive difference between two documents."""

    category: str = Field(..., description="Category of difference (e.g. 'liability', 'payment')")
    doc_a_text: str = Field("", description="Relevant text from document A")
    doc_b_text: str = Field("", description="Relevant text from document B")
    significance: str = Field("", description="Legal significance of the difference")
    recommendation: str = Field("", description="Recommended action")


class ComparisonResult(BaseModel):
    """Comparison results between two documents."""

    summary: str = Field("", description="High-level comparison summary")
    differences: list[DocumentDiff] = Field(default_factory=list)
    similarity_score: float = Field(0.0, ge=0.0, le=1.0)


_COMPARISON_PROMPT = """\
You are a legal analyst.  Compare the following two legal documents and
identify all substantive differences.  Focus on terms that create different
rights, obligations, or risks.

Return JSON matching this schema:
{schema}

--- DOCUMENT A ---
{text_a}

--- DOCUMENT B ---
{text_b}"""


class ComparisonTask(LegalTask):
    """
    Compare two legal documents and identify substantive differences.

    This task expects the second document to be passed as ``doc_b`` in kwargs::

        pipeline = TaskPipeline([ComparisonTask()])
        result_doc = pipeline.run(doc_a, doc_b=doc_b)

    Results are written to ``doc.extracted["comparison"]``.

    Parameters
    ----------
    llm_provider:
        LLM provider instance or name string.
    max_input_chars:
        Maximum characters per document sent to the LLM.
    """

    task_id = "comparison"
    doc_types: list[DocType] = []  # all types
    requires_llm = True

    def __init__(
        self,
        llm_provider: Any | None = None,
        max_input_chars: int = 8_000,
    ) -> None:
        self._llm_provider = llm_provider
        self._max_input_chars = max_input_chars
        self._provider: Any | None = None

    def _get_provider(self) -> Any:
        if self._provider is None:
            if isinstance(self._llm_provider, str):
                from contractex.core.extractors import ContractExtractor

                self._provider = ContractExtractor._create_provider(self._llm_provider)  # type: ignore[arg-type]
            elif self._llm_provider is not None:
                self._provider = self._llm_provider
            else:
                from contractex.core.extractors import ContractExtractor

                self._provider = ContractExtractor._create_provider("gpt-4o")  # type: ignore[arg-type]
        return self._provider

    def run(self, doc: LegalDoc, doc_b: LegalDoc | None = None, **kwargs: Any) -> LegalDoc:
        if not doc.full_text:
            return doc
        if doc_b is None or not doc_b.full_text:
            doc = doc.model_copy(update={
                "extracted": {
                    **doc.extracted,
                    "comparison": {"error": "doc_b not provided or has no text"},
                },
            })
            return doc

        import json

        schema_str = json.dumps(ComparisonResult.model_json_schema(), indent=2)
        prompt = _COMPARISON_PROMPT.format(
            schema=schema_str,
            text_a=doc.full_text[: self._max_input_chars],
            text_b=doc_b.full_text[: self._max_input_chars],
        )

        provider = self._get_provider()
        result = provider.extract_structured(prompt, ComparisonResult)

        doc = doc.model_copy(update={
            "extracted": {**doc.extracted, "comparison": result.model_dump()},
        })
        return doc


# Self-register
TaskRegistry.default().register(ComparisonTask)
