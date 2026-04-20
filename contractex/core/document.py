"""
LegalDoc — unified base model for all legal documents in ContractEx.

This module introduces ``LegalDoc`` as the single authoritative base class
for every document type handled by ContractEx pipelines.  It unifies the
previous ``Contract`` and ``LegalDocument`` hierarchies under one coherent
abstraction.

Migration notes
---------------
* ``LegalDocument`` in ``contractex.core.legal_document`` is now an alias
  for ``LegalDoc`` and will be removed in a future major release.
* ``Contract`` remains a typed subclass with strongly-typed fields for
  parties, clauses, financial terms, and risks.
* All pipeline components accept ``LegalDoc`` and return ``LegalDoc``
  (subclass-aware via ``doc_type``).
"""

from __future__ import annotations

import hashlib
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from contractex.core.legal_document import DocType, LegalDocumentMetadata, SourceSpan

# Re-export so callers can import from here directly
__all__ = [
    "LegalDoc",
    "LegalDocMetadata",
    "DocType",
    "SourceSpan",
]

# Alias for backward compatibility and conciseness
LegalDocMetadata = LegalDocumentMetadata


class LegalDoc(BaseModel):
    """
    Unified base model for all legal documents processed by ContractEx.

    Every document that passes through a ContractEx pipeline is represented
    as a ``LegalDoc`` (or a typed subclass).  The ``doc_type`` field acts as
    the discriminator for routing and rendering logic.

    Key design principles
    ---------------------
    * **Privacy first** — ``privacy_profile`` is attached at construction and
      travels with the document through every pipeline stage.  The
      ``PrivacyAwareLLMRouter`` reads it before any external API call.
    * **Provenance everywhere** — ``provenance`` maps every extracted field
      to a ``SourceSpan`` (chunk ID, page, char offsets, verbatim snippet).
    * **Composable** — ``extracted`` is a free-form dict so task outputs can
      be layered without subclassing.  Typed subclasses (``Contract``) overlay
      strongly-typed fields on top.
    * **Confidence aware** — ``confidences`` mirrors ``extracted`` so routing
      and review queues can be applied field-by-field.

    Attributes
    ----------
    doc_id:          Stable UUID string assigned at construction if not supplied.
    doc_type:        Primary document classification (``DocType`` enum).
    jurisdiction:    Jurisdiction code (e.g. ``"US-Federal"``, ``"CA-ON"``).
    language:        BCP-47 language code (default ``"en"``).
    full_text:       Full extracted plain text of the document.
    metadata:        Provenance and processing metadata.
    privacy_profile: Privacy controls — routing, sensitivity, redaction state.
                     Populated lazily; callers should always attach one before
                     passing the document to a pipeline that calls an LLM.
    extracted:       Free-form extraction results keyed by field name.
    confidences:     Per-field confidence scores (mirrors ``extracted``).
    provenance:      Maps field names to ``SourceSpan`` records.
    tags:            Arbitrary string tags for filtering and grouping.
    """

    model_config = ConfigDict(populate_by_name=True)

    # --- Identity ---------------------------------------------------------
    doc_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Stable UUID assigned at construction",
    )
    doc_type: DocType = Field(DocType.UNKNOWN, description="Primary document classification")

    # --- Legal coordinates ------------------------------------------------
    jurisdiction: str | None = Field(
        None,
        description=(
            "Flat jurisdiction string for backward compatibility "
            "(e.g. 'US-Federal', 'DE-BY').  For new code, prefer "
            "``jurisdiction_tag`` which carries the full hierarchy."
        ),
    )
    # Structured jurisdiction — populated by loaders/tasks; overrides the
    # flat string for filtering and conflict detection.
    # Using Any to avoid circular imports with contractex.taxonomy.
    jurisdiction_tag: Any | None = Field(
        None,
        description=(
            "Structured JurisdictionTag (country, region, court_system, applicability). "
            "Populated automatically from ``jurisdiction`` when ``jurisdiction_tag`` "
            "is None.  Pass a JurisdictionTag instance directly for full control."
        ),
    )
    # Authority profile — used by LegalRAGPipeline for weighted retrieval.
    # Using Any to avoid circular imports with contractex.taxonomy.
    authority_profile: Any | None = Field(
        None,
        description=(
            "AuthorityProfile (AuthorityLevel + jurisdiction + court_name). "
            "Drives authority-weighted retrieval scoring in LegalRAGPipeline."
        ),
    )
    language: str = Field("en", description="BCP-47 language code")

    # --- Content ----------------------------------------------------------
    full_text: str = Field("", description="Full extracted plain text")

    # --- Metadata & privacy -----------------------------------------------
    metadata: LegalDocMetadata = Field(
        default_factory=LegalDocMetadata,
        description="Provenance and processing metadata",
    )
    # Privacy profile — injected by PIIDetector / caller before LLM routing.
    # Using Any here to avoid circular imports with contractex.privacy; the
    # actual type is contractex.privacy.profile.PrivacyProfile.
    privacy_profile: Any | None = Field(
        None,
        description=(
            "PrivacyProfile attached to this document.  Controls LLM routing, "
            "redaction strategy, and GDPR retention.  None means no explicit "
            "controls — pipelines may apply defaults."
        ),
    )

    # --- Extraction results -----------------------------------------------
    extracted: dict[str, Any] = Field(
        default_factory=dict,
        description="Task extraction results (field_name → value)",
    )
    confidences: dict[str, float] = Field(
        default_factory=dict,
        description="Per-field confidence scores (mirrors extracted)",
    )
    provenance: dict[str, SourceSpan] = Field(
        default_factory=dict,
        description="Maps field names to SourceSpan records",
    )

    # --- Tags -------------------------------------------------------------
    tags: list[str] = Field(default_factory=list, description="Arbitrary tags")

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
    def effective_jurisdiction_tag(self) -> Any | None:
        """
        Return the ``JurisdictionTag`` for this document.

        If ``jurisdiction_tag`` is already set, returns it directly.
        Otherwise parses the flat ``jurisdiction`` string on-the-fly.
        Returns ``None`` when neither field is populated.
        """
        if self.jurisdiction_tag is not None:
            return self.jurisdiction_tag
        if self.jurisdiction:
            try:
                from contractex.taxonomy.jurisdiction import JurisdictionTag

                return JurisdictionTag.from_string(self.jurisdiction)
            except Exception:
                return None
        return None

    @property
    def authority_weight(self) -> float:
        """
        Normalised authority weight [0.01, 1.00] for retrieval scoring.

        Returns 0.01 (``AuthorityLevel.UNKNOWN``) when no ``authority_profile``
        is attached.
        """
        if self.authority_profile is not None:
            return float(getattr(self.authority_profile, "authority_weight", 0.01))
        return 0.01

    @property
    def provenance_coverage(self) -> float:
        """Fraction of ``extracted`` fields that have a ``SourceSpan``."""
        total = len(self.extracted)
        if not total:
            return 1.0
        covered = sum(1 for k in self.extracted if k in self.provenance)
        return covered / total

    @property
    def is_privacy_restricted(self) -> bool:
        """True if a PrivacyProfile is attached and routing is not 'any'."""
        if self.privacy_profile is None:
            return False
        routing = getattr(self.privacy_profile, "llm_routing", "any")
        return routing != "any"

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def set_field(
        self,
        field_name: str,
        value: Any,
        confidence: float = 0.0,
        *,
        chunk_id: str | None = None,
        source_url: str | None = None,
        page: int | None = None,
        char_start: int | None = None,
        char_end: int | None = None,
        snippet: str | None = None,
    ) -> None:
        """
        Set an extracted field together with its confidence score and
        optional provenance span in a single call.
        """
        self.extracted[field_name] = value
        self.confidences[field_name] = confidence
        if chunk_id is not None:
            self.provenance[field_name] = SourceSpan(
                chunk_id=chunk_id,
                source_url=source_url or self.metadata.source_url,
                page=page,
                char_start=char_start,
                char_end=char_end,
                snippet=snippet,
            )

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
        """Record a ``SourceSpan`` for *field_name*."""
        self.provenance[field_name] = SourceSpan(
            chunk_id=chunk_id,
            source_url=source_url or self.metadata.source_url,
            page=page,
            char_start=char_start,
            char_end=char_end,
            snippet=snippet,
        )

    def merge(self, other: LegalDoc) -> LegalDoc:
        """
        Return a new ``LegalDoc`` that merges *other*'s extracted fields and
        provenance into ``self``.  Fields in *other* overwrite ``self`` on
        collision.  Immutable identity fields (``doc_id``, ``doc_type``,
        ``full_text``) are taken from ``self``.
        """
        merged_extracted = {**self.extracted, **other.extracted}
        merged_confidences = {**self.confidences, **other.confidences}
        merged_provenance = {**self.provenance, **other.provenance}
        merged_tags = list(dict.fromkeys(self.tags + other.tags))
        return self.model_copy(
            update={
                "extracted": merged_extracted,
                "confidences": merged_confidences,
                "provenance": merged_provenance,
                "tags": merged_tags,
            }
        )
