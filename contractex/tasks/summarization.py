"""Summarization task — LLM-powered document summary."""

from __future__ import annotations

from typing import Any

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry

_SUMMARIZATION_PROMPT = """\
You are a legal analyst.  Summarize the following legal document in clear,
plain English.  Be concise (3–5 sentences).  Identify: document type, parties
(if any), key obligations, and the main legal purpose.

Document:
{text}

Summary:"""


class SummarizationTask(LegalTask):
    """
    Generate a concise plain-English summary of the document using an LLM.

    Results are written to ``doc.extracted["summary"]``.

    Parameters
    ----------
    llm_provider:
        LLM provider instance or name string.
    max_input_chars:
        Maximum characters sent to the LLM.  Defaults to 12 000 (~3 k tokens).
    """

    task_id = "summarization"
    doc_types: list[DocType] = []  # all types
    requires_llm = True

    def __init__(
        self,
        llm_provider: Any | None = None,
        max_input_chars: int = 12_000,
    ) -> None:
        self._llm_provider = llm_provider
        self._max_input_chars = max_input_chars
        self._provider: Any | None = None

    def _get_provider(self) -> Any:
        if self._provider is None:
            if isinstance(self._llm_provider, str):
                from contractex.core.extractors import ContractExtractor

                self._provider = ContractExtractor._create_provider(
                    self._llm_provider  # type: ignore[arg-type]
                )
            elif self._llm_provider is not None:
                self._provider = self._llm_provider
            else:
                from contractex.core.extractors import ContractExtractor

                self._provider = ContractExtractor._create_provider("gpt-4o")  # type: ignore[arg-type]
        return self._provider

    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        if not doc.full_text:
            return doc

        text = doc.full_text[: self._max_input_chars]
        prompt = _SUMMARIZATION_PROMPT.format(text=text)

        provider = self._get_provider()
        summary = provider.complete(prompt, temperature=0.3)

        doc = doc.model_copy(
            update={
                "extracted": {**doc.extracted, "summary": summary.strip()},
            }
        )
        return doc


# Self-register
TaskRegistry.default().register(SummarizationTask)
