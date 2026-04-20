"""
Confidence-based routing for extracted fields.

Routes extraction outputs to one of three queues based on per-field confidence
scores:

  * AUTO_ACCEPT  — confidence ≥ ``accept_threshold``  → proceed automatically
  * HUMAN_REVIEW — ``reject_threshold`` ≤ confidence < ``accept_threshold``
                   → route to human review queue
  * AUTO_REJECT  — confidence < ``reject_threshold``  → drop / flag

Per-field threshold overrides allow tighter rules for high-stakes fields
(e.g. passport number: (0.95, 0.75)) and looser ones for cosmetic fields.

Usage::

    router = ConfidenceRouter(
        accept_threshold=0.80,
        reject_threshold=0.40,
        field_thresholds={"passport_number": (0.95, 0.70)},
    )

    # Route a single field
    item = router.route_field("surname", "SMITH", confidence=0.93)
    print(item.decision)  # RoutingDecision.AUTO_ACCEPT

    # Route a whole LegalDocument
    result = router.route_document(document)
    if result.needs_review:
        audit.log_review_request(document.doc_id, result.review_field_names)

    # Route a plain dict (pre-LegalDocument pipelines)
    result = router.route_dict(fields, confidences)
    accepted = result.accepted   # {field_name: value}
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from contractex.core.legal_document import LegalDocument, SourceSpan

# ---------------------------------------------------------------------------
# Enumerations and data models
# ---------------------------------------------------------------------------


class RoutingDecision(str, Enum):
    """The routing outcome for a single extracted field."""

    AUTO_ACCEPT = "auto_accept"
    HUMAN_REVIEW = "human_review"
    AUTO_REJECT = "auto_reject"


class ReviewItem(BaseModel):
    """A single field that has been routed (to any queue)."""

    field_name: str = Field(..., description="Name of the extracted field")
    value: Any = Field(..., description="Extracted value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence")
    decision: RoutingDecision = Field(..., description="Routing decision")
    reason: str = Field(..., description="Human-readable explanation of the decision")
    document_id: str | None = Field(None, description="Parent document identifier")
    source_span: SourceSpan | None = Field(
        None,
        description="Source location of this field (if tracked by ProvenanceTracker)",
    )


class RoutingResult(BaseModel):
    """
    The outcome of routing all fields in a document or dict.

    Attributes:
        document_id:  Identifier of the document being routed.
        accepted:     Fields that cleared the auto-accept threshold
                      ``{field_name: value}``.
        review_queue: Fields requiring human review (ordered by confidence asc).
        rejected:     Fields that fell below the auto-reject threshold.
    """

    document_id: str | None = None
    accepted: dict[str, Any] = Field(default_factory=dict)
    review_queue: list[ReviewItem] = Field(default_factory=list)
    rejected: list[ReviewItem] = Field(default_factory=list)

    @property
    def needs_review(self) -> bool:
        return len(self.review_queue) > 0

    @property
    def fully_accepted(self) -> bool:
        return not self.review_queue and not self.rejected

    @property
    def acceptance_rate(self) -> float:
        """Fraction of total fields that were auto-accepted."""
        total = len(self.accepted) + len(self.review_queue) + len(self.rejected)
        return len(self.accepted) / total if total else 0.0

    @property
    def review_field_names(self) -> list[str]:
        """Names of fields in the review queue."""
        return [item.field_name for item in self.review_queue]

    @property
    def rejected_field_names(self) -> list[str]:
        """Names of rejected fields."""
        return [item.field_name for item in self.rejected]

    def summary(self) -> str:
        return (
            f"RoutingResult("
            f"accepted={len(self.accepted)}, "
            f"review={len(self.review_queue)}, "
            f"rejected={len(self.rejected)}, "
            f"acceptance_rate={self.acceptance_rate:.0%})"
        )


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class ConfidenceRouter:
    """
    Routes extracted fields based on per-field confidence scores.

    The default thresholds are calibrated for typical IDP use-cases:

    * ``accept_threshold = 0.80`` — require high confidence before automation
    * ``reject_threshold = 0.40`` — discard clearly unreliable extractions

    For safety-critical fields (passport number, date-of-birth) you should
    tighten per-field thresholds::

        router = ConfidenceRouter(
            field_thresholds={
                "passport_number": (0.95, 0.75),
                "date_of_birth":   (0.90, 0.60),
            }
        )

    Args:
        accept_threshold:  Global minimum confidence for auto-accept.
        reject_threshold:  Global maximum confidence for auto-reject.
        field_thresholds:  Per-field overrides ``{field: (accept, reject)}``.

    Raises:
        ValueError: If ``reject_threshold >= accept_threshold``.
    """

    def __init__(
        self,
        accept_threshold: float = 0.80,
        reject_threshold: float = 0.40,
        field_thresholds: dict[str, tuple[float, float]] | None = None,
    ) -> None:
        if not (0.0 <= reject_threshold < accept_threshold <= 1.0):
            raise ValueError(
                "Thresholds must satisfy 0 ≤ reject_threshold < accept_threshold ≤ 1; "
                f"got reject={reject_threshold}, accept={accept_threshold}"
            )
        self.accept_threshold = accept_threshold
        self.reject_threshold = reject_threshold
        self.field_thresholds: dict[str, tuple[float, float]] = field_thresholds or {}

    # ------------------------------------------------------------------
    # Single-field routing
    # ------------------------------------------------------------------

    def route_field(
        self,
        field_name: str,
        value: Any,
        confidence: float,
        document_id: str | None = None,
        source_span: SourceSpan | None = None,
    ) -> ReviewItem:
        """
        Route a single (field_name, value, confidence) triple.

        Returns a ``ReviewItem`` with the routing decision and its rationale.
        """
        accept_t, reject_t = self.field_thresholds.get(
            field_name, (self.accept_threshold, self.reject_threshold)
        )

        if confidence >= accept_t:
            decision = RoutingDecision.AUTO_ACCEPT
            reason = f"confidence {confidence:.2f} ≥ accept threshold {accept_t:.2f}"
        elif confidence >= reject_t:
            decision = RoutingDecision.HUMAN_REVIEW
            reason = (
                f"confidence {confidence:.2f} in review band " f"[{reject_t:.2f}, {accept_t:.2f})"
            )
        else:
            decision = RoutingDecision.AUTO_REJECT
            reason = f"confidence {confidence:.2f} < reject threshold {reject_t:.2f}"

        return ReviewItem(
            field_name=field_name,
            value=value,
            confidence=confidence,
            decision=decision,
            reason=reason,
            document_id=document_id,
            source_span=source_span,
        )

    # ------------------------------------------------------------------
    # Document-level routing
    # ------------------------------------------------------------------

    def route_document(self, document: LegalDocument) -> RoutingResult:
        """
        Route all ``extracted_fields`` in a ``LegalDocument``.

        Populates ``result.accepted``, ``result.review_queue``, and
        ``result.rejected``.  The review queue is sorted by confidence
        ascending so reviewers see the least-certain items first.
        """
        result = RoutingResult(document_id=document.doc_id)

        for field_name, value in document.extracted_fields.items():
            confidence = document.field_confidences.get(field_name, 0.0)
            span = document.provenance.get(field_name)
            item = self.route_field(
                field_name,
                value,
                confidence,
                document_id=document.doc_id,
                source_span=span,
            )
            if item.decision == RoutingDecision.AUTO_ACCEPT:
                result.accepted[field_name] = value
            elif item.decision == RoutingDecision.HUMAN_REVIEW:
                result.review_queue.append(item)
            else:
                result.rejected.append(item)

        # Least-confident first so reviewers prioritise the worst items
        result.review_queue.sort(key=lambda i: i.confidence)

        return result

    # ------------------------------------------------------------------
    # Dict-level routing (pre-LegalDocument pipelines)
    # ------------------------------------------------------------------

    def route_dict(
        self,
        fields: dict[str, Any],
        confidences: dict[str, float],
        document_id: str | None = None,
    ) -> RoutingResult:
        """
        Route a plain ``{field_name: value}`` dict.

        Useful when integrating the router into pipelines that produce raw
        dicts before constructing a ``LegalDocument``.

        Args:
            fields:      Extracted field values.
            confidences: Per-field confidence scores (default 0.0 for missing).
            document_id: Optional parent document identifier.
        """
        result = RoutingResult(document_id=document_id)

        for field_name, value in fields.items():
            confidence = confidences.get(field_name, 0.0)
            item = self.route_field(
                field_name,
                value,
                confidence,
                document_id=document_id,
            )
            if item.decision == RoutingDecision.AUTO_ACCEPT:
                result.accepted[field_name] = value
            elif item.decision == RoutingDecision.HUMAN_REVIEW:
                result.review_queue.append(item)
            else:
                result.rejected.append(item)

        result.review_queue.sort(key=lambda i: i.confidence)

        return result

    def __repr__(self) -> str:
        return (
            f"ConfidenceRouter("
            f"accept={self.accept_threshold}, "
            f"reject={self.reject_threshold}, "
            f"field_overrides={len(self.field_thresholds)})"
        )
