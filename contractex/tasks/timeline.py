"""Timeline extraction task — pulls dates and events from legal documents."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry


class TimelineEvent(BaseModel):
    """A single dated event extracted from a legal document."""

    date: str = Field(..., description="ISO-8601 or natural language date")
    event: str = Field(..., description="Plain-English description of the event")
    significance: str = Field("", description="Why this date matters legally")
    source_snippet: str = Field("", description="Verbatim source text")


class TimelineResult(BaseModel):
    """All timeline events extracted from a document."""

    events: list[TimelineEvent] = Field(default_factory=list)


_TIMELINE_PROMPT = """\
You are a legal analyst.  Extract all legally significant dates and deadlines
from the following document.  For each date, describe the event and its legal
significance.

Return JSON matching this schema:
{schema}

Document:
{text}"""


class TimelineTask(LegalTask):
    """
    Extract a chronological timeline of legally significant dates.

    Results are written to ``doc.extracted["timeline"]`` as a list of
    ``TimelineEvent`` dicts.

    Parameters
    ----------
    llm_provider:
        LLM provider instance or name string.
    """

    task_id = "timeline"
    doc_types: list[DocType] = []  # all types
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

        schema_str = json.dumps(TimelineResult.model_json_schema(), indent=2)
        prompt = _TIMELINE_PROMPT.format(schema=schema_str, text=doc.full_text[:12_000])

        provider = self._get_provider()
        result = provider.extract_structured(prompt, TimelineResult)

        doc = doc.model_copy(
            update={
                "extracted": {
                    **doc.extracted,
                    "timeline": [e.model_dump() for e in result.events],
                },
            }
        )
        return doc


# Self-register
TaskRegistry.default().register(TimelineTask)
