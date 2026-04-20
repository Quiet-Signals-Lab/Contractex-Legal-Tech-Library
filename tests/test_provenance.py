"""
Unit tests for ProvenanceTracker and ChunkRecord.

All tests are pure Python — no network, no LLM, no database.
"""

import pytest

from contractex.core.legal_document import LegalDocument, SourceSpan
from contractex.utils.provenance import ChunkRecord, ProvenanceTracker


# ---------------------------------------------------------------------------
# ChunkRecord
# ---------------------------------------------------------------------------


class TestChunkRecord:
    def test_content_hash_computed(self):
        record = ChunkRecord(chunk_id="c-0000-abc", text="hello world")
        assert len(record.content_hash) == 64  # SHA-256 hex

    def test_content_hash_deterministic(self):
        r1 = ChunkRecord(chunk_id="c-0000-abc", text="same text")
        r2 = ChunkRecord(chunk_id="c-0001-abc", text="same text")
        assert r1.content_hash == r2.content_hash

    def test_length(self):
        record = ChunkRecord(chunk_id="c-0000-abc", text="hello")
        assert record.length == 5

    def test_repr(self):
        record = ChunkRecord(chunk_id="c-0000-abc", text="hi", char_start=0, char_end=2, page=1)
        assert "c-0000-abc" in repr(record)


# ---------------------------------------------------------------------------
# ProvenanceTracker — registration
# ---------------------------------------------------------------------------


class TestProvenanceTrackerRegistration:
    def test_register_single_chunk(self):
        tracker = ProvenanceTracker(source_url="https://example.com")
        records = tracker.register_chunks(["The quick brown fox"])
        assert len(records) == 1
        assert records[0].source_url == "https://example.com"
        assert records[0].char_start == 0
        assert records[0].char_end == len("The quick brown fox")

    def test_register_multiple_chunks_offsets(self):
        tracker = ProvenanceTracker()
        chunks = ["Hello", "World"]
        records = tracker.register_chunks(chunks)
        assert records[0].char_start == 0
        assert records[0].char_end == 5
        # +1 for separator
        assert records[1].char_start == 6
        assert records[1].char_end == 11

    def test_chunk_ids_are_deterministic(self):
        t1 = ProvenanceTracker()
        t2 = ProvenanceTracker()
        r1 = t1.register_chunks(["same text"])
        r2 = t2.register_chunks(["same text"])
        assert r1[0].chunk_id == r2[0].chunk_id

    def test_chunk_ids_differ_for_different_text(self):
        tracker = ProvenanceTracker()
        records = tracker.register_chunks(["text A", "text B"])
        assert records[0].chunk_id != records[1].chunk_id

    def test_page_map_applied(self):
        tracker = ProvenanceTracker()
        records = tracker.register_chunks(["Page 1 text", "Page 2 text"], page_map={0: 1, 1: 2})
        assert records[0].page == 1
        assert records[1].page == 2

    def test_source_url_override(self):
        tracker = ProvenanceTracker(source_url="https://default.com")
        records = tracker.register_chunks(["text"], source_url="https://override.com")
        assert records[0].source_url == "https://override.com"

    def test_register_chunk_convenience(self):
        tracker = ProvenanceTracker()
        record = tracker.register_chunk("single chunk", page=5)
        assert record.page == 5
        assert len(tracker) == 1

    def test_len(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["a", "b", "c"])
        assert len(tracker) == 3

    def test_clear_resets_state(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["text"])
        tracker.clear()
        assert len(tracker) == 0

    def test_accumulates_across_calls(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["first"])
        tracker.register_chunks(["second"])
        assert len(tracker) == 2


# ---------------------------------------------------------------------------
# ProvenanceTracker — span resolution (exact match)
# ---------------------------------------------------------------------------


class TestFindSpanExact:
    def setup_method(self):
        self.tracker = ProvenanceTracker(source_url="https://example.com")
        self.chunks = [
            "Section 1: The parties agree to pay monthly fees.",
            "Section 2: Termination requires thirty days notice.",
            "Section 3: Governing law is the state of Delaware.",
        ]
        self.tracker.register_chunks(self.chunks, page_map={0: 1, 1: 2, 2: 3})

    def test_exact_match_first_chunk(self):
        span = self.tracker.find_span("monthly fees")
        assert span is not None
        assert span.page == 1

    def test_exact_match_last_chunk(self):
        span = self.tracker.find_span("state of Delaware")
        assert span is not None
        assert span.page == 3

    def test_exact_match_full_chunk_text(self):
        full = "Section 2: Termination requires thirty days notice."
        span = self.tracker.find_span(full)
        assert span is not None
        assert span.page == 2

    def test_char_offsets_correct(self):
        # "monthly fees" starts at position 33 in chunk 0
        query = "monthly fees"
        span = self.tracker.find_span(query)
        assert span is not None
        assert span.char_end - span.char_start == len(query)

    def test_snippet_populated(self):
        span = self.tracker.find_span("monthly fees")
        assert span is not None
        assert "monthly fees" in span.snippet

    def test_no_match_returns_none(self):
        span = self.tracker.find_span("this text is not in any chunk")
        assert span is None

    def test_empty_query_returns_none(self):
        assert self.tracker.find_span("") is None

    def test_whitespace_only_returns_none(self):
        assert self.tracker.find_span("   ") is None


# ---------------------------------------------------------------------------
# ProvenanceTracker — span resolution (Jaccard fallback)
# ---------------------------------------------------------------------------


class TestFindSpanJaccard:
    def test_paraphrased_text_matches(self):
        tracker = ProvenanceTracker(similarity_threshold=0.5)
        tracker.register_chunks(["The contract shall be governed by the laws of New York."])
        # Paraphrased — not an exact substring
        span = tracker.find_span("governed by laws of New York contract")
        assert span is not None

    def test_below_threshold_returns_none(self):
        tracker = ProvenanceTracker(similarity_threshold=0.99)
        tracker.register_chunks(["The contract shall be governed by the laws of New York."])
        # Low overlap — should not match at 0.99 threshold
        span = tracker.find_span("completely different words that share almost nothing")
        assert span is None


# ---------------------------------------------------------------------------
# ProvenanceTracker — annotate helpers
# ---------------------------------------------------------------------------


class TestAnnotate:
    def test_annotate_success(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["Payment is due within 30 days."])
        doc = LegalDocument()
        doc.extracted_fields["payment_term"] = "30 days"
        result = tracker.annotate(doc, "payment_term", "30 days")
        assert result is True
        assert "payment_term" in doc.provenance

    def test_annotate_failure(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["Payment is due within 30 days."])
        doc = LegalDocument()
        result = tracker.annotate(doc, "nonexistent", "text not in chunks")
        assert result is False
        assert "nonexistent" not in doc.provenance

    def test_annotate_all_strings(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["Name: John Smith. DOB: 1990-01-15."])
        doc = LegalDocument()
        doc.extracted_fields = {"name": "John Smith", "dob": "1990-01-15"}
        results = tracker.annotate_all(doc)
        assert results["name"] is True
        assert results["dob"] is True
        assert len(doc.provenance) == 2

    def test_annotate_all_non_string_skipped(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["some text"])
        doc = LegalDocument()
        doc.extracted_fields = {"count": 42, "flag": True}
        results = tracker.annotate_all(doc)
        # Non-string fields cannot be matched
        assert results["count"] is False
        assert results["flag"] is False


# ---------------------------------------------------------------------------
# ProvenanceTracker — coverage stats
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_coverage_all_found(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["surname GARCIA given_name JOSE"])
        doc = LegalDocument()
        doc.extracted_fields = {"surname": "GARCIA", "given_name": "JOSE"}
        tracker.annotate_all(doc)
        stats = tracker.coverage(doc)
        assert stats["coverage_ratio"] == 1.0
        assert stats["fields_with_provenance"] == 2

    def test_coverage_partial(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["surname GARCIA"])
        doc = LegalDocument()
        doc.extracted_fields = {"surname": "GARCIA", "dob": "1990-01-15"}
        tracker.annotate_all(doc)
        stats = tracker.coverage(doc)
        assert stats["coverage_ratio"] == pytest.approx(0.5)

    def test_coverage_no_fields(self):
        tracker = ProvenanceTracker()
        doc = LegalDocument()
        stats = tracker.coverage(doc)
        assert stats["coverage_ratio"] == 1.0


# ---------------------------------------------------------------------------
# ProvenanceTracker — get_chunk and repr
# ---------------------------------------------------------------------------


class TestGetChunkAndRepr:
    def test_get_chunk_by_id(self):
        tracker = ProvenanceTracker()
        records = tracker.register_chunks(["hello"])
        found = tracker.get_chunk(records[0].chunk_id)
        assert found is not None
        assert found.text == "hello"

    def test_get_chunk_missing(self):
        tracker = ProvenanceTracker()
        assert tracker.get_chunk("nonexistent-id") is None

    def test_chunks_property_is_copy(self):
        tracker = ProvenanceTracker()
        tracker.register_chunks(["a", "b"])
        chunks = tracker.chunks
        chunks.clear()
        assert len(tracker) == 2  # original unmodified

    def test_repr(self):
        tracker = ProvenanceTracker(source_url="https://example.com")
        tracker.register_chunks(["text"])
        r = repr(tracker)
        assert "ProvenanceTracker" in r
        assert "chunks=1" in r
