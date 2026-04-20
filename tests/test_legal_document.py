"""
Unit tests for LegalDocument, DocType, SourceSpan, and LegalDocumentMetadata.

No LLM, no database, no network — pure Pydantic model tests.
"""

import pytest

from contractex.core.legal_document import (
    DocType,
    LegalDocument,
    LegalDocumentMetadata,
    SourceSpan,
)


# ---------------------------------------------------------------------------
# DocType
# ---------------------------------------------------------------------------


class TestDocType:
    def test_values_are_strings(self):
        assert DocType.STATUTE == "statute"
        assert DocType.IDENTITY_DOC == "identity_doc"

    def test_unknown_default(self):
        doc = LegalDocument()
        assert doc.doc_type == DocType.UNKNOWN


# ---------------------------------------------------------------------------
# SourceSpan
# ---------------------------------------------------------------------------


class TestSourceSpan:
    def test_basic_creation(self):
        span = SourceSpan(
            chunk_id="chunk-0001-ab12",
            source_url="https://example.com/doc.pdf",
            page=3,
            char_start=100,
            char_end=200,
            snippet="the extracted text",
        )
        assert span.chunk_id == "chunk-0001-ab12"
        assert span.page == 3

    def test_snippet_truncated_to_300_chars(self):
        long_text = "x" * 500
        span = SourceSpan(chunk_id="c-0000-00000000", snippet=long_text)
        assert len(span.snippet) == 300

    def test_snippet_short_not_truncated(self):
        span = SourceSpan(chunk_id="c-0000-00000000", snippet="short")
        assert span.snippet == "short"

    def test_str_representation(self):
        span = SourceSpan(chunk_id="c-0000-ab12", page=5)
        assert "p5" in str(span)

    def test_str_representation_no_page(self):
        span = SourceSpan(chunk_id="c-0000-ab12", char_start=10)
        assert "@10" in str(span)


# ---------------------------------------------------------------------------
# LegalDocument — creation and defaults
# ---------------------------------------------------------------------------


class TestLegalDocumentCreation:
    def test_minimal_document(self):
        doc = LegalDocument()
        assert doc.doc_type == DocType.UNKNOWN
        assert doc.extracted_fields == {}
        assert doc.field_confidences == {}
        assert doc.provenance == {}
        assert doc.language == "en"

    def test_full_document(self):
        doc = LegalDocument(
            doc_type=DocType.STATUTE,
            title="17 U.S.C. § 107",
            jurisdiction="US-Federal",
            citation="17 U.S.C. § 107",
            hierarchy_path=["Title 17", "Chapter 1", "§ 107"],
            effective_date="1976-10-19",
            full_text="Notwithstanding the provisions of sections 106 ...",
            language="en",
        )
        assert doc.doc_type == DocType.STATUTE
        assert doc.jurisdiction == "US-Federal"
        assert doc.hierarchy_path == ["Title 17", "Chapter 1", "§ 107"]

    def test_jurisdiction_stripped(self):
        doc = LegalDocument(jurisdiction="  US-Federal  ")
        assert doc.jurisdiction == "US-Federal"

    def test_none_jurisdiction_preserved(self):
        doc = LegalDocument(jurisdiction=None)
        assert doc.jurisdiction is None


# ---------------------------------------------------------------------------
# LegalDocument — computed properties
# ---------------------------------------------------------------------------


class TestLegalDocumentProperties:
    def test_content_hash_none_without_text(self):
        doc = LegalDocument()
        assert doc.content_hash is None

    def test_content_hash_present_with_text(self):
        doc = LegalDocument(full_text="some text")
        assert doc.content_hash is not None
        assert len(doc.content_hash) == 64  # SHA-256 hex

    def test_content_hash_deterministic(self):
        doc1 = LegalDocument(full_text="same text")
        doc2 = LegalDocument(full_text="same text")
        assert doc1.content_hash == doc2.content_hash

    def test_provenance_coverage_no_fields(self):
        doc = LegalDocument()
        assert doc.provenance_coverage == 1.0

    def test_provenance_coverage_partial(self):
        doc = LegalDocument()
        doc.extracted_fields = {"a": 1, "b": 2, "c": 3}
        doc.provenance["a"] = SourceSpan(chunk_id="c-0000-00000000")
        assert doc.provenance_coverage == pytest.approx(1 / 3)

    def test_provenance_coverage_full(self):
        doc = LegalDocument()
        doc.extracted_fields = {"a": 1}
        doc.provenance["a"] = SourceSpan(chunk_id="c-0000-00000000")
        assert doc.provenance_coverage == 1.0


# ---------------------------------------------------------------------------
# LegalDocument — mutation helpers
# ---------------------------------------------------------------------------


class TestLegalDocumentMutations:
    def test_add_provenance(self):
        doc = LegalDocument(
            metadata=LegalDocumentMetadata(source_url="https://example.com")
        )
        doc.add_provenance(
            "citation",
            chunk_id="chunk-0001-ab12",
            page=2,
            snippet="§ 107",
        )
        assert "citation" in doc.provenance
        span = doc.provenance["citation"]
        assert span.chunk_id == "chunk-0001-ab12"
        assert span.page == 2
        assert span.snippet == "§ 107"
        # source_url falls back to metadata.source_url
        assert span.source_url == "https://example.com"

    def test_add_provenance_explicit_url(self):
        doc = LegalDocument()
        doc.add_provenance(
            "field",
            chunk_id="c-0000-00000000",
            source_url="https://explicit.com",
        )
        assert doc.provenance["field"].source_url == "https://explicit.com"

    def test_set_field(self):
        doc = LegalDocument()
        span = SourceSpan(chunk_id="c-0000-00000000")
        doc.set_field("surname", "SMITH", confidence=0.95, span=span)
        assert doc.extracted_fields["surname"] == "SMITH"
        assert doc.field_confidences["surname"] == 0.95
        assert doc.provenance["surname"] == span

    def test_set_field_without_span(self):
        doc = LegalDocument()
        doc.set_field("given_name", "JOHN", confidence=0.88)
        assert "given_name" in doc.extracted_fields
        assert "given_name" not in doc.provenance


# ---------------------------------------------------------------------------
# LegalDocument — serialisation
# ---------------------------------------------------------------------------


class TestLegalDocumentSerialisation:
    def test_to_dict(self):
        doc = LegalDocument(doc_type=DocType.CASE_OPINION, citation="Smith v. Jones")
        d = doc.to_dict()
        assert d["doc_type"] == "case_opinion"
        assert d["citation"] == "Smith v. Jones"

    def test_to_json_roundtrip(self):
        doc = LegalDocument(
            doc_type=DocType.REGULATION,
            jurisdiction="US-Federal",
            extracted_fields={"authority": "EPA"},
            field_confidences={"authority": 0.90},
        )
        json_str = doc.to_json()
        restored = LegalDocument.model_validate_json(json_str)
        assert restored.doc_type == DocType.REGULATION
        assert restored.extracted_fields["authority"] == "EPA"

    def test_to_json_write_file(self, tmp_path):
        doc = LegalDocument(title="Test Doc")
        path = str(tmp_path / "doc.json")
        doc.to_json(file_path=path)
        import json
        with open(path) as f:
            data = json.load(f)
        assert data["title"] == "Test Doc"

    def test_str_and_repr(self):
        doc = LegalDocument(doc_type=DocType.STATUTE, citation="17 U.S.C. § 107")
        assert "statute" in str(doc)
        assert "17 U.S.C. § 107" in str(doc)
        assert "LegalDocument" in repr(doc)
