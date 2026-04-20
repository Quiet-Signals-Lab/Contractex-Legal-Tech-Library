"""Obligation extraction task — identifies duties and obligations in legal text."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry


class Obligation(BaseModel):
    """A single obligation or duty extracted from a legal document."""

    obligor: str = Field(..., description="The party that must act")
    obligee: str = Field("", description="The party the duty is owed to")
    action: str = Field(..., description="What must be done")
    trigger: str = Field("", description="Condition that activates this obligation")
    deadline: str = Field("", description="When the obligation must be fulfilled")
    consequence: str = Field("", description="Consequence of non-compliance")
    source_snippet: str = Field("", description="Verbatim source text")


class ObligationsResult(BaseModel):
    """All obligations extracted from a document."""

    obligations: list[Obligation] = Field(default_factory=list)


_OBLIGATIONS_PROMPT = """\
You are a legal analyst specialising in contract obligations.  Extract all
obligations, duties, and requirements from the following document.  For each,
identify who must act, what they must do, and when.

Return JSON matching this schema:
{schema}

Document:
{text}"""


class ObligationsTask(LegalTask):
    """
    Extract obligations and duties from legal documents.

    Results are written to ``doc.extracted["obligations"]`` as a list of
    ``Obligation`` dicts.

    Parameters
    ----------
    llm_provider:
        LLM provider instance or name string.
    """

    task_id = "obligations"
    doc_types = [DocType.CONTRACT, DocType.STATUTE, DocType.REGULATION, DocType.PLEADING]
    requires_llm = True

    def __init__(self, llm_provider: Any | None = None) -> None:
        self._llm_provider = llm_provider
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

    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        if not doc.full_text:
            return doc

        import json

        schema_str = json.dumps(ObligationsResult.model_json_schema(), indent=2)
        prompt = _OBLIGATIONS_PROMPT.format(
            schema=schema_str, text=doc.full_text[:12_000]
        )

        provider = self._get_provider()
        result = provider.extract_structured(prompt, ObligationsResult)

        doc = doc.model_copy(update={
            "extracted": {
                **doc.extracted,
                "obligations": [o.model_dump() for o in result.obligations],
            },
        })
        return doc


# Self-register
TaskRegistry.default().register(ObligationsTask)
