"""
Unit tests for ConfidenceRouter, RoutingDecision, ReviewItem, and RoutingResult.

No LLM, no network, no database.
"""

from __future__ import annotations

import pytest

from contractex.core.legal_document import LegalDocument, SourceSpan
from contractex.utils.routing import (
    ConfidenceRouter,
    ReviewItem,
    RoutingDecision,
    RoutingResult,
)

# ---------------------------------------------------------------------------
# ConfidenceRouter — construction
# ---------------------------------------------------------------------------


class TestConfidenceRouterConstruction:
    def test_default_thresholds(self):
        router = ConfidenceRouter()
        assert router.accept_threshold == 0.80
        assert router.reject_threshold == 0.40

    def test_custom_thresholds(self):
        router = ConfidenceRouter(accept_threshold=0.90, reject_threshold=0.50)
        assert router.accept_threshold == 0.90
        assert router.reject_threshold == 0.50

    def test_invalid_thresholds_raise(self):
        with pytest.raises(ValueError, match="reject_threshold"):
            ConfidenceRouter(accept_threshold=0.40, reject_threshold=0.80)

    def test_equal_thresholds_raise(self):
        with pytest.raises(ValueError):
            ConfidenceRouter(accept_threshold=0.70, reject_threshold=0.70)

    def test_repr(self):
        router = ConfidenceRouter()
        assert "ConfidenceRouter" in repr(router)


# ---------------------------------------------------------------------------
# ConfidenceRouter.route_field — single field routing
# ---------------------------------------------------------------------------


class TestRouteField:
    def setup_method(self):
        self.router = ConfidenceRouter(
            accept_threshold=0.80,
            reject_threshold=0.40,
        )

    def test_high_confidence_accepted(self):
        item = self.router.route_field("surname", "SMITH", confidence=0.95)
        assert item.decision == RoutingDecision.AUTO_ACCEPT

    def test_boundary_accept(self):
        item = self.router.route_field("surname", "SMITH", confidence=0.80)
        assert item.decision == RoutingDecision.AUTO_ACCEPT

    def test_mid_confidence_review(self):
        item = self.router.route_field("dob", "1990-01-15", confidence=0.60)
        assert item.decision == RoutingDecision.HUMAN_REVIEW

    def test_boundary_review_upper(self):
        # Just below accept threshold
        item = self.router.route_field("dob", "1990-01-15", confidence=0.799)
        assert item.decision == RoutingDecision.HUMAN_REVIEW

    def test_boundary_review_lower(self):
        # Exactly at reject threshold → still review (reject_t <= conf < accept_t)
        item = self.router.route_field("dob", "1990-01-15", confidence=0.40)
        assert item.decision == RoutingDecision.HUMAN_REVIEW

    def test_low_confidence_rejected(self):
        item = self.router.route_field("passport_number", "X123", confidence=0.20)
        assert item.decision == RoutingDecision.AUTO_REJECT

    def test_zero_confidence_rejected(self):
        item = self.router.route_field("field", "value", confidence=0.0)
        assert item.decision == RoutingDecision.AUTO_REJECT

    def test_reason_populated(self):
        item = self.router.route_field("field", "value", confidence=0.95)
        assert len(item.reason) > 0

    def test_document_id_attached(self):
        item = self.router.route_field("field", "v", confidence=0.9, document_id="doc-1")
        assert item.document_id == "doc-1"

    def test_source_span_attached(self):
        span = SourceSpan(chunk_id="c-0000-00000000")
        item = self.router.route_field("field", "v", confidence=0.9, source_span=span)
        assert item.source_span == span


# ---------------------------------------------------------------------------
# ConfidenceRouter — per-field threshold overrides
# ---------------------------------------------------------------------------


class TestFieldThresholdOverrides:
    def test_per_field_accept_threshold(self):
        router = ConfidenceRouter(
            accept_threshold=0.80,
            reject_threshold=0.40,
            field_thresholds={"passport_number": (0.95, 0.70)},
        )
        # 0.85 passes global but not the passport_number override
        item = router.route_field("passport_number", "AB123456", confidence=0.85)
        assert item.decision == RoutingDecision.HUMAN_REVIEW

    def test_per_field_reject_threshold(self):
        router = ConfidenceRouter(
            accept_threshold=0.80,
            reject_threshold=0.40,
            field_thresholds={"passport_number": (0.95, 0.70)},
        )
        # 0.65 < 0.70 (passport_number reject threshold) → AUTO_REJECT
        # even though 0.65 > 0.40 (global reject threshold)
        item = router.route_field("passport_number", "AB123456", confidence=0.65)
        assert item.decision == RoutingDecision.AUTO_REJECT

    def test_per_field_review_band(self):
        router = ConfidenceRouter(
            accept_threshold=0.80,
            reject_threshold=0.40,
            field_thresholds={"passport_number": (0.95, 0.70)},
        )
        # 0.80 ≥ 0.70 (passport reject) but < 0.95 (passport accept) → HUMAN_REVIEW
        item = router.route_field("passport_number", "AB123456", confidence=0.80)
        assert item.decision == RoutingDecision.HUMAN_REVIEW

    def test_per_field_override_does_not_affect_other_fields(self):
        router = ConfidenceRouter(
            accept_threshold=0.80,
            field_thresholds={"passport_number": (0.95, 0.70)},
        )
        item = router.route_field("given_name", "JOSE", confidence=0.85)
        assert item.decision == RoutingDecision.AUTO_ACCEPT


# ---------------------------------------------------------------------------
# ConfidenceRouter.route_document
# ---------------------------------------------------------------------------


class TestRouteDocument:
    def _make_doc(self) -> LegalDocument:
        doc = LegalDocument(doc_id="doc-1")
        doc.extracted_fields = {
            "surname": "GARCIA",  # high confidence → accept
            "given_name": "JOSE",  # mid confidence → review
            "passport_number": "X1234",  # low confidence → reject
        }
        doc.field_confidences = {
            "surname": 0.95,
            "given_name": 0.60,
            "passport_number": 0.15,
        }
        return doc

    def test_partitions_into_three_buckets(self):
        router = ConfidenceRouter()
        doc = self._make_doc()
        result = router.route_document(doc)
        assert "surname" in result.accepted
        assert any(i.field_name == "given_name" for i in result.review_queue)
        assert any(i.field_name == "passport_number" for i in result.rejected)

    def test_needs_review_true(self):
        router = ConfidenceRouter()
        result = router.route_document(self._make_doc())
        assert result.needs_review is True

    def test_fully_accepted_false(self):
        router = ConfidenceRouter()
        result = router.route_document(self._make_doc())
        assert result.fully_accepted is False

    def test_fully_accepted_when_all_pass(self):
        router = ConfidenceRouter()
        doc = LegalDocument(doc_id="doc-2")
        doc.extracted_fields = {"a": 1, "b": 2}
        doc.field_confidences = {"a": 0.99, "b": 0.95}
        result = router.route_document(doc)
        assert result.fully_accepted is True

    def test_review_queue_sorted_by_confidence_ascending(self):
        router = ConfidenceRouter()
        doc = LegalDocument()
        doc.extracted_fields = {"low": "x", "mid": "y"}
        doc.field_confidences = {"low": 0.45, "mid": 0.65}
        result = router.route_document(doc)
        confidences = [item.confidence for item in result.review_queue]
        assert confidences == sorted(confidences)

    def test_acceptance_rate(self):
        router = ConfidenceRouter()
        result = router.route_document(self._make_doc())
        # 1 accepted / 3 total = 1/3
        assert result.acceptance_rate == pytest.approx(1 / 3)

    def test_review_field_names(self):
        router = ConfidenceRouter()
        result = router.route_document(self._make_doc())
        assert "given_name" in result.review_field_names

    def test_provenance_span_attached(self):
        router = ConfidenceRouter()
        doc = LegalDocument()
        doc.extracted_fields = {"name": "SMITH"}
        doc.field_confidences = {"name": 0.60}
        doc.provenance["name"] = SourceSpan(chunk_id="c-0000-00000000")
        result = router.route_document(doc)
        review_item = result.review_queue[0]
        assert review_item.source_span is not None

    def test_document_id_propagated(self):
        router = ConfidenceRouter()
        doc = LegalDocument(doc_id="my-doc")
        doc.extracted_fields = {"field": "val"}
        doc.field_confidences = {"field": 0.60}
        result = router.route_document(doc)
        assert result.review_queue[0].document_id == "my-doc"


# ---------------------------------------------------------------------------
# ConfidenceRouter.route_dict
# ---------------------------------------------------------------------------


class TestRouteDict:
    def test_basic_routing(self):
        router = ConfidenceRouter()
        fields = {"name": "SMITH", "dob": "1990-01-15", "number": "X123"}
        confidences = {"name": 0.95, "dob": 0.60, "number": 0.10}
        result = router.route_dict(fields, confidences, document_id="doc-X")
        assert "name" in result.accepted
        assert any(i.field_name == "dob" for i in result.review_queue)
        assert any(i.field_name == "number" for i in result.rejected)

    def test_missing_confidence_defaults_to_zero(self):
        router = ConfidenceRouter()
        result = router.route_dict({"field": "val"}, {})
        assert any(i.field_name == "field" for i in result.rejected)

    def test_summary_string(self):
        ConfidenceRouter()
        result = RoutingResult()
        assert "RoutingResult" in result.summary()


# ---------------------------------------------------------------------------
# ReviewItem
# ---------------------------------------------------------------------------


class TestReviewItem:
    def test_creation(self):
        item = ReviewItem(
            field_name="surname",
            value="GARCIA",
            confidence=0.60,
            decision=RoutingDecision.HUMAN_REVIEW,
            reason="in review band",
        )
        assert item.field_name == "surname"
        assert item.decision == RoutingDecision.HUMAN_REVIEW
