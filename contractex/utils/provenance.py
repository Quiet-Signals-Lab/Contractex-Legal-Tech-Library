"""
Provenance tracking for document extraction pipelines.

Connects extracted field values back to the specific chunk — and character
offsets within it — that they came from.  This enables:

  * Citation fidelity  (Job 1 — legal RAG: cite the exact statute paragraph)
  * Field-level audit trails (Job 2 — IDP: passport field ← page 1, lines 3-4)
  * Hallucination detection (generation references chunk that doesn't exist)

Usage::

    tracker = ProvenanceTracker(source_url="https://ecfr.gov/...")
    records = tracker.register_chunks(chunks)       # from your chunker

    # After LLM extraction:
    span = tracker.find_span("the extracted text fragment")
    if span:
        document.add_provenance("liability_clause", span.chunk_id,
                                page=span.page, snippet=span.snippet)

    # Or use the one-liner annotate():
    tracker.annotate(document, "liability_clause", extracted_text)
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field

from contractex.core.legal_document import LegalDocument, SourceSpan

logger = logging.getLogger(__name__)

_SNIPPET_MAX = 200   # characters in a SourceSpan snippet
_SIM_THRESHOLD_DEFAULT = 0.85


# ---------------------------------------------------------------------------
# ChunkRecord
# ---------------------------------------------------------------------------


@dataclass
class ChunkRecord:
    """
    Metadata about a text chunk registered with the tracker.

    Attributes:
        chunk_id:    Stable, deterministic identifier (index + content hash).
        text:        Raw chunk text.
        source_url:  Canonical URL of the source document.
        page:        1-based page number this chunk belongs to, if known.
        char_start:  Character offset of this chunk's first char in the full doc.
        char_end:    Character offset after this chunk's last char.
        content_hash: SHA-256 of ``text``.
    """

    chunk_id: str
    text: str
    source_url: str | None = None
    page: int | None = None
    char_start: int = 0
    char_end: int = 0
    content_hash: str = field(init=False)

    def __post_init__(self) -> None:
        self.content_hash = hashlib.sha256(self.text.encode()).hexdigest()

    @property
    def length(self) -> int:
        return len(self.text)

    def __repr__(self) -> str:
        return (
            f"ChunkRecord(id={self.chunk_id!r}, "
            f"chars={self.char_start}:{self.char_end}, "
            f"page={self.page})"
        )


# ---------------------------------------------------------------------------
# ProvenanceTracker
# ---------------------------------------------------------------------------


class ProvenanceTracker:
    """
    Registers text chunks and resolves extracted values back to source spans.

    Resolution strategy
    -------------------
    1. **Exact substring** — O(n) scan per chunk; preferred.
    2. **Jaccard token overlap** — bag-of-words similarity for paraphrased or
       truncated values; only returns a match when the score exceeds
       ``similarity_threshold`` (default 0.85) to avoid false attributions.

    The tracker is stateful: every call to ``register_chunks()`` appends to
    the internal chunk list and advances the global character offset.  Call
    ``clear()`` to reset between documents.

    Args:
        source_url:           Default source URL attached to registered chunks.
        similarity_threshold: Jaccard threshold for the fallback matcher.
    """

    def __init__(
        self,
        source_url: str | None = None,
        similarity_threshold: float = _SIM_THRESHOLD_DEFAULT,
    ) -> None:
        self.source_url = source_url
        self.similarity_threshold = similarity_threshold
        self._chunks: list[ChunkRecord] = []
        self._global_offset: int = 0

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register_chunks(
        self,
        chunks: list[str],
        source_url: str | None = None,
        page_map: dict[int, int] | None = None,
    ) -> list[ChunkRecord]:
        """
        Register an ordered list of text chunks.

        Args:
            chunks:     Text chunks (e.g. output of ``ClauseAwareChunker``).
            source_url: Override the tracker-level source URL for this batch.
            page_map:   Optional mapping of chunk index → 1-based page number.

        Returns:
            The list of ``ChunkRecord`` objects created for these chunks.
        """
        url = source_url or self.source_url
        records: list[ChunkRecord] = []

        for idx, text in enumerate(chunks):
            global_idx = len(self._chunks)
            record = ChunkRecord(
                chunk_id=self._make_id(global_idx, text),
                text=text,
                source_url=url,
                page=page_map.get(idx) if page_map else None,
                char_start=self._global_offset,
                char_end=self._global_offset + len(text),
            )
            self._chunks.append(record)
            # +1 represents the separator that the chunker inserts between chunks
            self._global_offset += len(text) + 1
            records.append(record)

        logger.debug(
            "Registered %d chunk(s); total=%d, global_offset=%d",
            len(records),
            len(self._chunks),
            self._global_offset,
        )
        return records

    def register_chunk(
        self,
        text: str,
        source_url: str | None = None,
        page: int | None = None,
    ) -> ChunkRecord:
        """Register a single chunk.  Convenience wrapper around ``register_chunks``."""
        page_map = {0: page} if page is not None else None
        return self.register_chunks([text], source_url=source_url, page_map=page_map)[0]

    # ------------------------------------------------------------------
    # Span resolution
    # ------------------------------------------------------------------

    def find_span(self, extracted_text: str) -> SourceSpan | None:
        """
        Resolve *extracted_text* to a ``SourceSpan``.

        Returns ``None`` if no chunk matches above the similarity threshold.

        Pass 1 — exact substring search (fast, preferred).
        Pass 2 — Jaccard token overlap (fallback for paraphrased values).
        """
        if not extracted_text or not self._chunks:
            return None

        query = extracted_text.strip()
        if not query:
            return None

        # --- Pass 1: exact substring ---
        for record in self._chunks:
            idx = record.text.find(query)
            if idx != -1:
                abs_start = record.char_start + idx
                return SourceSpan(
                    chunk_id=record.chunk_id,
                    source_url=record.source_url,
                    page=record.page,
                    char_start=abs_start,
                    char_end=abs_start + len(query),
                    snippet=query[:_SNIPPET_MAX],
                )

        # --- Pass 2: Jaccard token overlap ---
        query_tokens = set(query.lower().split())
        if not query_tokens:
            return None

        best_score = 0.0
        best_record: ChunkRecord | None = None

        for record in self._chunks:
            chunk_tokens = set(record.text.lower().split())
            if not chunk_tokens:
                continue
            intersection = query_tokens & chunk_tokens
            union = query_tokens | chunk_tokens
            score = len(intersection) / len(union)
            if score > best_score:
                best_score = score
                best_record = record

        if best_score >= self.similarity_threshold and best_record is not None:
            logger.debug(
                "Jaccard fallback match (score=%.2f) for %r → chunk %s",
                best_score,
                query[:40],
                best_record.chunk_id,
            )
            return SourceSpan(
                chunk_id=best_record.chunk_id,
                source_url=best_record.source_url,
                page=best_record.page,
                char_start=best_record.char_start,
                char_end=best_record.char_end,
                snippet=query[:_SNIPPET_MAX],
            )

        logger.debug(
            "No provenance match for %r (best_score=%.2f < threshold=%.2f)",
            query[:40],
            best_score,
            self.similarity_threshold,
        )
        return None

    # ------------------------------------------------------------------
    # Annotation helper
    # ------------------------------------------------------------------

    def annotate(
        self,
        document: LegalDocument,
        field_name: str,
        extracted_text: str,
    ) -> bool:
        """
        Resolve *extracted_text* to a span and attach it to *document*.

        Sets ``document.provenance[field_name]`` if a match is found.

        Returns:
            True if provenance was attached, False if no match was found.
        """
        span = self.find_span(extracted_text)
        if span is not None:
            document.provenance[field_name] = span
            return True
        return False

    def annotate_all(
        self,
        document: LegalDocument,
    ) -> dict[str, bool]:
        """
        Annotate every field in ``document.extracted_fields``.

        Values must be strings (or string-coercible).

        Returns:
            Dict mapping field_name → whether provenance was found.
        """
        results: dict[str, bool] = {}
        for field_name, value in document.extracted_fields.items():
            if isinstance(value, str):
                results[field_name] = self.annotate(document, field_name, value)
            else:
                results[field_name] = False
        return results

    # ------------------------------------------------------------------
    # Statistics / diagnostics
    # ------------------------------------------------------------------

    def coverage(self, document: LegalDocument) -> dict[str, float]:
        """
        Provenance coverage statistics for *document*.

        Returns:
            ``{"fields_with_provenance": int, "total_fields": int, "coverage_ratio": float}``
        """
        total = len(document.extracted_fields)
        covered = sum(1 for k in document.extracted_fields if k in document.provenance)
        return {
            "fields_with_provenance": covered,
            "total_fields": total,
            "coverage_ratio": covered / total if total else 1.0,
        }

    # ------------------------------------------------------------------
    # Chunk access
    # ------------------------------------------------------------------

    @property
    def chunks(self) -> list[ChunkRecord]:
        """Read-only view of registered chunks."""
        return list(self._chunks)

    def get_chunk(self, chunk_id: str) -> ChunkRecord | None:
        """Retrieve a chunk by its ID.  Returns None if not found."""
        for record in self._chunks:
            if record.chunk_id == chunk_id:
                return record
        return None

    def clear(self) -> None:
        """Reset tracker state (call between documents)."""
        self._chunks.clear()
        self._global_offset = 0

    def __len__(self) -> int:
        return len(self._chunks)

    def __repr__(self) -> str:
        return (
            f"ProvenanceTracker(chunks={len(self._chunks)}, "
            f"source_url={self.source_url!r})"
        )

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _make_id(index: int, text: str) -> str:
        """Deterministic chunk ID: zero-padded index + 8-char content hash."""
        h = hashlib.sha256(text.encode()).hexdigest()[:8]
        return f"chunk-{index:04d}-{h}"
