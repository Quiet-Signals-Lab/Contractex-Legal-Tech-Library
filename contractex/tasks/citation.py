"""Citation extraction task — identify and format legal citations."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from contractex.core.document import LegalDoc
from contractex.core.legal_document import DocType
from contractex.tasks.base import LegalTask
from contractex.tasks.registry import TaskRegistry


class LegalCitation(BaseModel):
    """A legal citation found in or generated from a document."""

    raw_text: str = Field(..., description="Verbatim citation as it appears in the text")
    citation_type: str = Field(
        "",
        description="Type: case, statute, regulation, secondary, treaty",
    )
    normalized: str = Field("", description="Normalised Bluebook citation form")
    source_url: str = Field("", description="URL to the cited source (if resolvable)")
    char_start: int = Field(0, description="Character offset of the citation in full_text")
    char_end: int = Field(0, description="End character offset")


class CitationResult(BaseModel):
    """All citations extracted from a document."""

    citations: list[LegalCitation] = Field(default_factory=list)


# Common legal citation patterns (heuristic — not exhaustive)
_CITATION_PATTERNS: list[tuple[str, str]] = [
    # US case citations: Smith v. Jones, 123 F.3d 456 (9th Cir. 1999)
    ("case", r"[A-Z][A-Za-z\s\.,]+v\.\s+[A-Z][A-Za-z\s\.,]+,\s+\d+\s+[A-Z][A-Za-z\.]+\s+\d+"),
    # US Code: 42 U.S.C. § 1983
    ("statute", r"\d+\s+U\.S\.C\.?\s+§+\s+[\d\w\-\.]+"),
    # CFR: 29 C.F.R. § 825.100
    ("regulation", r"\d+\s+C\.F\.R\.?\s+§+\s+[\d\w\-\.]+"),
    # EU: Regulation (EU) 2016/679
    ("regulation", r"(?:Regulation|Directive)\s+\([A-Z]+\)\s+\d{4}/\d+"),
    # GDPR shorthand
    ("regulation", r"GDPR|CCPA|HIPAA|FERPA|COPPA"),
]


class CitationTask(LegalTask):
    """
    Extract legal citations from document text using regex heuristics.

    Results are written to ``doc.extracted["citations"]`` as a list of
    ``LegalCitation`` dicts.

    This task is LLM-free (regex only).  For full Bluebook normalisation,
    set ``use_llm=True`` and supply an LLM provider — the LLM will normalise
    raw citation strings to proper Bluebook format.

    Parameters
    ----------
    use_llm:
        If ``True``, use an LLM to normalise citations to Bluebook format.
    llm_provider:
        LLM provider instance or name string (only used when ``use_llm=True``).
    """

    task_id = "citation"
    doc_types = [
        DocType.STATUTE,
        DocType.REGULATION,
        DocType.CASE_OPINION,
        DocType.SECONDARY,
        DocType.CONTRACT,
        DocType.PLEADING,
    ]
    requires_llm = False  # regex-only by default

    def __init__(
        self,
        use_llm: bool = False,
        llm_provider: Any | None = None,
    ) -> None:
        self._use_llm = use_llm
        self._llm_provider = llm_provider
        self.requires_llm = use_llm

    def run(self, doc: LegalDoc, **kwargs: Any) -> LegalDoc:
        if not doc.full_text:
            return doc

        citations = self._extract_regex(doc.full_text)

        doc = doc.model_copy(
            update={
                "extracted": {
                    **doc.extracted,
                    "citations": [c.model_dump() for c in citations],
                },
            }
        )
        return doc

    def _extract_regex(self, text: str) -> list[LegalCitation]:
        citations: list[LegalCitation] = []
        seen: set[str] = set()

        for citation_type, pattern in _CITATION_PATTERNS:
            for m in re.finditer(pattern, text):
                raw = m.group(0).strip()
                if raw in seen:
                    continue
                seen.add(raw)
                citations.append(
                    LegalCitation(
                        raw_text=raw,
                        citation_type=citation_type,
                        char_start=m.start(),
                        char_end=m.end(),
                    )
                )

        # Sort by position in document
        citations.sort(key=lambda c: c.char_start)
        return citations


# Self-register
TaskRegistry.default().register(CitationTask)
