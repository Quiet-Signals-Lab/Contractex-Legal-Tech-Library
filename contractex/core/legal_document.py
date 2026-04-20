"""
LegalDocument — general-purpose model for legal document intelligence.

While ``Contract`` (models.py) models bilateral agreements,
``LegalDocument`` covers the full breadth of document types processed by
ContractEx pipelines:

  * Statutes and regulations (Job 1 — legal RAG)
  * Case opinions and secondary sources (Job 1)
  * Identity documents, government forms (Job 2 — IDP / immigration)

Both share the same LLM and loader infrastructure.  The ``provenance`` dict
gives every extracted field a ``SourceSpan`` reference, enabling citation
fidelity and GDPR-grade audit trails.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class DocType(str, Enum):
    """Primary document classification."""

    STATUTE = "statute"
    REGULATION = "regulation"
    CASE_OPINION = "case_opinion"
    SECONDARY = "secondary"           # encyclopedia, commentary, overview
    IDENTITY_DOC = "identity_doc"     # passport, national ID, driver's licence
    GOVERNMENT_FORM = "government_form"
    CONTRACT = "contract"
    PLEADING = "pleading"
    CORRESPONDENCE = "correspondence"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Provenance primitives
# ---------------------------------------------------------------------------


class SourceSpan(BaseModel):
    """
    Precise provenance reference for a single extracted field or text span.

    Maps a piece of extracted information back to its exact origin so that
    consumers can verify, cite, or re-read the raw text.

    Attributes:
        chunk_id:    Stable ID of the source chunk (assigned by ProvenanceTracker).
        source_url:  Canonical URL of the source document.
        page:        1-based page number in the source document.
        char_start:  Character offset of the match start within the full document.
        char_end:    Character offset of the match end.
        snippet:     Short verbatim excerpt (≤ 300 chars) from the source.
    """

    chunk_id: str = Field(..., description="Stable ID of the source chunk")
    source_url: str | None = Field(None, description="Canonical source URL")
    page: int | None = Field(None, ge=1, description="1-based page number")
    char_start: int | None = Field(None, ge=0, description="Char offset start")
    char_end: int | None = Field(None, ge=0, description="Char offset end")
    snippet: str | None = Field(
        None,
        description="Verbatim excerpt from the source (≤ 300 chars)",
    )

    @field_validator("snippet")
    @classmethod
    def _truncate_snippet(cls, v: str | None) -> str | None:
        return v[:300] if v and len(v) > 300 else v

    def __str__(self) -> str:
        loc = f"p{self.page}" if self.page else f"@{self.char_start}"
        return f"SourceSpan({self.chunk_id}, {loc})"


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------


class LegalDocumentMetadata(BaseModel):
    """Provenance and processing metadata for a LegalDocument."""

    # Fetch provenance
    source_url: str | None = Field(None, description="Canonical URL of the source")
    retrieval_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the document was fetched",
    )
    content_hash: str | None = Field(
        None,
        description="SHA-256 of the raw source content (for deduplication)",
    )
    etag: str | None = Field(
        None,
        description="HTTP ETag captured at fetch time (for conditional GETs)",
    )
    last_modified: str | None = Field(
        None,
        description="HTTP Last-Modified header value at fetch time",
    )

    # Processing provenance
    llm_provider: str | None = None
    llm_model: str | None = None
    processing_time_seconds: float | None = None
    token_usage: dict[str, int] | None = None
    warnings: list[str] = Field(default_factory=list)

    # User-defined metadata
    custom_fields: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Main model
# ---------------------------------------------------------------------------


class LegalDocument(BaseModel):
    """
    General-purpose model for any legal document processed by ContractEx.

    Design principles
    -----------------
    * **Provenance first** — every extracted field can be traced to its
      exact source location via ``provenance[field_name]`` → ``SourceSpan``.
    * **Schema-agnostic extraction** — ``extracted_fields`` holds a plain
      dict of doc-type–specific values; callers overlay typed sub-schemas
      (e.g. ``PassportData``) on top as needed.
    * **Confidence aware** — ``field_confidences`` mirrors ``extracted_fields``
      with per-field confidence scores consumed by ``ConfidenceRouter``.

    Example::

        doc = LegalDocument(
            doc_type=DocType.STATUTE,
            title="17 U.S.C. § 107 — Fair Use",
            jurisdiction="US-Federal",
            citation="17 U.S.C. § 107",
            hierarchy_path=["Title 17", "Chapter 1", "§ 107"],
            metadata=LegalDocumentMetadata(
                source_url="https://www.law.cornell.edu/uscode/text/17/107"
            ),
        )
        doc.extracted_fields["governing_body"] = "Congress"
        doc.field_confidences["governing_body"] = 0.97
        doc.add_provenance("governing_body", chunk_id="chunk-0000-ab12",
                           page=1, snippet="enacted by Congress …")
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "doc_type": "statute",
                "title": "17 U.S.C. § 107 — Fair Use",
                "jurisdiction": "US-Federal",
                "citation": "17 U.S.C. § 107",
                "hierarchy_path": ["Title 17", "Chapter 1", "§ 107"],
                "effective_date": "1976-10-19",
            }
        }
    )

    # --- Identity ---------------------------------------------------------
    doc_type: DocType = Field(DocType.UNKNOWN, description="Document classification")
    title: str | None = Field(None, description="Document title or heading")
    doc_id: str | None = Field(
        None,
        description="Stable identifier assigned by the ingestion pipeline",
    )

    # --- Legal coordinates ------------------------------------------------
    jurisdiction: str | None = Field(
        None,
        description="Jurisdiction code (e.g. 'US-Federal', 'CA-ON', 'ES')",
    )
    citation: str | None = Field(
        None,
        description="Formal citation string (Bluebook, MRZ reference, etc.)",
    )
    hierarchy_path: list[str] = Field(
        default_factory=list,
        description="Path from root to this document (title → chapter → section)",
    )

    # --- Dates ------------------------------------------------------------
    effective_date: str | None = Field(
        None,
        description="ISO-8601 effective / issued date",
    )
    expiration_date: str | None = Field(
        None,
        description="ISO-8601 expiry date (if applicable)",
    )
    amended_date: str | None = Field(
        None,
        description="Date of most recent amendment",
    )

    # --- Content ----------------------------------------------------------
    full_text: str | None = Field(None, description="Full extracted text")
    summary: str | None = Field(None, description="LLM-generated summary")
    language: str = Field("en", description="BCP-47 language code")

    # --- Extracted fields & confidence ------------------------------------
    extracted_fields: dict[str, Any] = Field(
        default_factory=dict,
        description=(
            "Schema-validated extracted data (doc-type specific). "
            "E.g. for a passport: {'surname': 'SMITH', 'given_name': 'JOHN', ...}"
        ),
    )
    field_confidences: dict[str, float] = Field(
        default_factory=dict,
        description="Per-field confidence scores (keys mirror extracted_fields)",
    )

    # --- Provenance -------------------------------------------------------
    provenance: dict[str, SourceSpan] = Field(
        default_factory=dict,
        description=(
            "Maps field names (or arbitrary span labels) to their SourceSpan "
            "records.  Populated by ProvenanceTracker.annotate()."
        ),
    )

    # --- Metadata ---------------------------------------------------------
    metadata: LegalDocumentMetadata = Field(
        default_factory=LegalDocumentMetadata,
    )

    # --- Tags -------------------------------------------------------------
    tags: list[str] = Field(default_factory=list)

    # ------------------------------------------------------------------
    # Validators
    # ------------------------------------------------------------------

    @field_validator("jurisdiction")
    @classmethod
    def _normalise_jurisdiction(cls, v: str | None) -> str | None:
        return v.strip() if v else v

    # ------------------------------------------------------------------
    # Computed properties
    # ------------------------------------------------------------------

    @property
    def content_hash(self) -> str | None:
        """SHA-256 of ``full_text`` for deduplication.  None if no text."""
        if self.full_text:
            return hashlib.sha256(self.full_text.encode()).hexdigest()
        return None

    @property
    def provenance_coverage(self) -> float:
        """Fraction of extracted_fields that have a SourceSpan record."""
        total = len(self.extracted_fields)
        if not total:
            return 1.0
        covered = sum(1 for k in self.extracted_fields if k in self.provenance)
        return covered / total

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def add_provenance(
        self,
        field_name: str,
        chunk_id: str,
        *,
        source_url: str | None = None,
        page: int | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
        snippet: str | None = None,
    ) -> None:
        """Record a SourceSpan for *field_name*."""
        self.provenance[field_name] = SourceSpan(
            chunk_id=chunk_id,
            source_url=source_url or self.metadata.source_url,
            page=page,
            char_start=char_start,
            char_end=char_end,
            snippet=snippet,
        )

    def set_field(
        self,
        field_name: str,
        value: Any,
        confidence: float,
        span: SourceSpan | None = None,
    ) -> None:
        """
        Convenience method to set an extracted field, its confidence, and
        optionally its provenance in one call.
        """
        self.extracted_fields[field_name] = value
        self.field_confidences[field_name] = confidence
        if span is not None:
            self.provenance[field_name] = span

    # ------------------------------------------------------------------
    # Export helpers
    # ------------------------------------------------------------------

    def to_json(self, file_path: str | None = None) -> str:
        """Serialise to JSON string, optionally writing to *file_path*."""
        json_str = self.model_dump_json(indent=2)
        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json_str)
        return json_str

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump()

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __str__(self) -> str:
        label = self.citation or self.title or self.doc_id or "unlabelled"
        return f"LegalDocument({self.doc_type.value}, {label!r})"

    def __repr__(self) -> str:
        return (
            f"LegalDocument(doc_type={self.doc_type!r}, "
            f"jurisdiction={self.jurisdiction!r}, "
            f"citation={self.citation!r}, "
            f"fields={len(self.extracted_fields)})"
        )
