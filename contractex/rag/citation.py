"""
Citation models and formatter for RAG responses.

Every answer from ``LegalRAGPipeline`` carries citations that map answer
fragments back to exact source spans.  This module defines:

* ``Citation``           — a single source reference attached to an answer.
* ``CitationFormatter``  — renders citations in Bluebook, inline, or footnote
                           style.

Bluebook format is the standard for US legal work and is required when
``citation_format="bluebook"`` is passed to ``LegalRAGPipeline``.

Usage::

    from contractex.rag.citation import Citation, CitationFormatter

    fmt = CitationFormatter()
    citation = Citation(
        text_fragment="data retention obligations",
        source_title="GDPR Article 5",
        source_url="https://gdpr-info.eu/art-5-gdpr/",
        source_span=span,
        citation_string="",
    )
    citation.citation_string = fmt.format_inline(citation)
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from contractex.core.legal_document import SourceSpan


class Citation(BaseModel):
    """
    A source reference attached to an answer fragment in a ``RAGResponse``.

    Attributes
    ----------
    text_fragment:
        The fragment of the answer text this citation supports.
    source_title:
        Human-readable title of the source document.
    source_url:
        Canonical URL of the source (may be ``None`` for local documents).
    source_span:
        Exact location in the source document (chunk, page, char offsets).
    citation_string:
        Formatted citation string (populated by ``CitationFormatter``).
    index:
        1-based citation number within the response (for footnote style).
    """

    text_fragment: str = Field(..., description="Answer fragment this citation supports")
    source_title: str = Field(..., description="Source document title")
    source_url: str | None = Field(None, description="Canonical source URL")
    source_span: SourceSpan | None = Field(None, description="Exact source location")
    citation_string: str = Field("", description="Formatted citation string")
    index: int = Field(1, description="1-based citation index within the response")


class CitationFormatter:
    """
    Render ``Citation`` objects in different legal citation styles.

    Supported styles
    ----------------
    * ``"inline"``    — ``(Source Title, p. N)`` appended to the fragment.
    * ``"footnote"``  — superscript ``[N]`` in text; full reference at the end.
    * ``"bluebook"``  — abbreviated Bluebook format (US legal standard).

    Usage::

        formatter = CitationFormatter()
        formatted = formatter.format(citation, style="bluebook")
    """

    def format(
        self,
        citation: Citation,
        style: Literal["inline", "footnote", "bluebook"] = "inline",
    ) -> str:
        """Return a formatted citation string for *citation*."""
        if style == "bluebook":
            return self.format_bluebook(citation)
        if style == "footnote":
            return self.format_footnote(citation)
        return self.format_inline(citation)

    def format_inline(self, citation: Citation) -> str:
        """``(Source Title, p. N)`` inline reference."""
        parts = [citation.source_title]
        if citation.source_span and citation.source_span.page:
            parts.append(f"p. {citation.source_span.page}")
        elif citation.source_url:
            parts.append(citation.source_url)
        return f"({', '.join(parts)})"

    def format_footnote(self, citation: Citation) -> str:
        """``[N] Source Title (URL, page N).``"""
        page = ""
        if citation.source_span and citation.source_span.page:
            page = f", p. {citation.source_span.page}"
        url = f" <{citation.source_url}>" if citation.source_url else ""
        return f"[{citation.index}] {citation.source_title}{url}{page}."

    def format_bluebook(self, citation: Citation) -> str:
        """
        Abbreviated Bluebook-style citation.

        Format: ``Source Title, at N (URL).``
        For statutes and regulations, callers should override this with a
        proper Bluebook citation form constructed from the document's metadata.
        """
        at_page = ""
        if citation.source_span and citation.source_span.page:
            at_page = f", at {citation.source_span.page}"
        url = f" ({citation.source_url})" if citation.source_url else ""
        return f"{citation.source_title}{at_page}{url}."

    def format_all(
        self,
        citations: list[Citation],
        style: Literal["inline", "footnote", "bluebook"] = "inline",
    ) -> list[str]:
        """Format a list of citations, setting ``index`` sequentially."""
        result = []
        for i, c in enumerate(citations, 1):
            c.index = i
            result.append(self.format(c, style=style))
        return result
