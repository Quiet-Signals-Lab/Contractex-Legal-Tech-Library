"""
Unit tests for database models.

These tests don't require a database connection - they test the domain
models in isolation.
"""
from datetime import datetime

import pytest

from contractex.storage.models import (
    Clause,
    ClauseType,
    Document,
    ProcessingLog,
    ProcessingStage,
    ProcessingStatus,
)

# ============================================================================
# Document Model Tests
# ============================================================================

@pytest.mark.unit
class TestDocumentModel:
    """Test Document domain model."""

    def test_document_creation(self, sample_document):
        """Test creating a Document instance."""
        assert sample_document.filename == "test_contract.pdf"
        assert sample_document.file_hash == "a1b2c3d4e5f6"
        assert sample_document.extracted_text.startswith("This is a test")
        assert sample_document.metadata["contract_type"] == "NDA"
        assert len(sample_document.metadata["parties"]) == 2

    def test_document_defaults(self):
        """Test Document default values."""
        doc = Document()
        assert doc.id is None
        assert doc.filename == ""
        assert doc.file_data is None
        assert doc.metadata == {}
        assert doc.uploaded_at is None

    def test_document_compute_hash(self):
        """Test SHA-256 hash computation."""
        data = b"test binary data"
        hash1 = Document.compute_hash(data)
        hash2 = Document.compute_hash(data)

        assert hash1 == hash2  # Deterministic
        assert len(hash1) == 64  # SHA-256 produces 64 hex chars
        assert hash1.isalnum()  # Only hex characters

    def test_document_compute_hash_different_data(self):
        """Test hash changes with different data."""
        hash1 = Document.compute_hash(b"data1")
        hash2 = Document.compute_hash(b"data2")
        assert hash1 != hash2

    def test_document_update_metadata(self, sample_document):
        """Test metadata update preserves existing values."""
        original_type = sample_document.metadata["contract_type"]
        sample_document.update_metadata(reviewed=True, reviewer="John Doe")

        assert sample_document.metadata["contract_type"] == original_type
        assert sample_document.metadata["reviewed"] is True
        assert sample_document.metadata["reviewer"] == "John Doe"

    def test_document_get_metadata_field(self, sample_document):
        """Test safe metadata field access."""
        assert sample_document.get_metadata_field("contract_type") == "NDA"
        assert sample_document.get_metadata_field("nonexistent") is None
        assert sample_document.get_metadata_field("nonexistent", "default") == "default"

    def test_document_from_db_row(self):
        """Test creating Document from database row."""
        row = (
            1,  # id
            "test.pdf",  # filename
            "hash123",  # file_hash
            b"data",  # file_data
            "text content",  # extracted_text
            {"key": "value"},  # metadata
            datetime(2024, 1, 1),  # uploaded_at
            datetime(2024, 1, 2)   # updated_at
        )

        doc = Document.from_db_row(row)

        assert doc.id == 1
        assert doc.filename == "test.pdf"
        assert doc.file_hash == "hash123"
        assert doc.file_data == b"data"
        assert doc.extracted_text == "text content"
        assert doc.metadata == {"key": "value"}
        assert doc.uploaded_at == datetime(2024, 1, 1)
        assert doc.updated_at == datetime(2024, 1, 2)


# ============================================================================
# Clause Model Tests
# ============================================================================

@pytest.mark.unit
class TestClauseModel:
    """Test Clause domain model."""

    def test_clause_creation(self, sample_clause):
        """Test creating a Clause instance."""
        assert sample_clause.document_id == 1
        assert sample_clause.clause_text.startswith("Party A shall pay")
        assert sample_clause.clause_type == "payment"
        assert sample_clause.page_number == 3
        assert sample_clause.confidence_score == 0.95

    def test_clause_defaults(self):
        """Test Clause default values."""
        clause = Clause()
        assert clause.id is None
        assert clause.document_id == 0
        assert clause.clause_text == ""
        assert clause.clause_type is None
        assert clause.metadata == {}

    def test_clause_has_bounding_box(self, sample_clause):
        """Test bounding box detection."""
        assert sample_clause.has_bounding_box() is True

        # Clause without bounding box
        clause_no_bbox = Clause(document_id=1, clause_text="test")
        assert clause_no_bbox.has_bounding_box() is False

    def test_clause_get_bounding_box(self, sample_clause):
        """Test bounding box retrieval."""
        bbox = sample_clause.get_bounding_box()

        assert bbox is not None
        assert bbox['x'] == 50.0
        assert bbox['y'] == 200.0
        assert bbox['width'] == 500.0
        assert bbox['height'] == 50.0

    def test_clause_get_bounding_box_incomplete(self):
        """Test bounding box returns None when incomplete."""
        clause = Clause(
            document_id=1,
            clause_text="test",
            bbox_x=50.0,
            # Missing other bbox coordinates
        )
        assert clause.get_bounding_box() is None

    def test_clause_from_db_row(self):
        """Test creating Clause from database row."""
        row = (
            1,  # id
            10,  # document_id
            "Clause text",  # clause_text
            "payment",  # clause_type
            5,  # page_number
            100.0,  # bbox_x
            200.0,  # bbox_y
            400.0,  # bbox_width
            50.0,   # bbox_height
            0.92,   # confidence_score
            None,   # parent_clause_id
            {"custom": "data"},  # metadata
            datetime(2024, 1, 1)  # created_at
        )

        clause = Clause.from_db_row(row)

        assert clause.id == 1
        assert clause.document_id == 10
        assert clause.clause_text == "Clause text"
        assert clause.clause_type == "payment"
        assert clause.page_number == 5
        assert clause.has_bounding_box() is True
        assert clause.confidence_score == 0.92
        assert clause.metadata == {"custom": "data"}


# ============================================================================
# ProcessingLog Model Tests
# ============================================================================

@pytest.mark.unit
class TestProcessingLogModel:
    """Test ProcessingLog domain model."""

    def test_processing_log_creation(self, sample_processing_log):
        """Test creating a ProcessingLog instance."""
        assert sample_processing_log.document_id == 1
        assert sample_processing_log.processing_stage == ProcessingStage.UPLOADED
        assert sample_processing_log.status == ProcessingStatus.COMPLETED
        assert sample_processing_log.error_message is None

    def test_processing_log_defaults(self):
        """Test ProcessingLog default values."""
        log = ProcessingLog()
        assert log.id is None
        assert log.document_id is None
        assert log.processing_stage == ""
        assert log.status == ""

    def test_processing_log_is_failed(self):
        """Test failure detection."""
        failed_log = ProcessingLog(
            document_id=1,
            processing_stage=ProcessingStage.EXTRACTED,
            status=ProcessingStatus.FAILED,
            error_message="Extraction failed"
        )
        assert failed_log.is_failed() is True

        success_log = ProcessingLog(
            document_id=1,
            processing_stage=ProcessingStage.EXTRACTED,
            status=ProcessingStatus.COMPLETED
        )
        assert success_log.is_failed() is False

    def test_processing_log_is_completed(self, sample_processing_log):
        """Test completion detection."""
        assert sample_processing_log.is_completed() is True

        pending_log = ProcessingLog(
            document_id=1,
            processing_stage=ProcessingStage.UPLOADED,
            status=ProcessingStatus.PENDING
        )
        assert pending_log.is_completed() is False

    def test_processing_log_from_db_row(self):
        """Test creating ProcessingLog from database row."""
        row = (
            1,  # id
            42,  # document_id
            "extracted",  # processing_stage
            "completed",  # status
            None,  # error_message
            datetime(2024, 1, 1)  # created_at
        )

        log = ProcessingLog.from_db_row(row)

        assert log.id == 1
        assert log.document_id == 42
        assert log.processing_stage == "extracted"
        assert log.status == "completed"
        assert log.error_message is None
        assert log.created_at == datetime(2024, 1, 1)


# ============================================================================
# Controlled Vocabulary Tests
# ============================================================================

@pytest.mark.unit
class TestControlledVocabularies:
    """Test controlled vocabulary constants."""

    def test_clause_types(self):
        """Test ClauseType constants."""
        assert ClauseType.PAYMENT == "payment"
        assert ClauseType.TERMINATION == "termination"
        assert ClauseType.CONFIDENTIALITY == "confidentiality"
        assert ClauseType.LIABILITY == "liability"
        assert ClauseType.INDEMNIFICATION == "indemnification"
        assert ClauseType.FORCE_MAJEURE == "force_majeure"

    def test_processing_stages(self):
        """Test ProcessingStage constants."""
        assert ProcessingStage.UPLOADED == "uploaded"
        assert ProcessingStage.EXTRACTED == "extracted"
        assert ProcessingStage.EMBEDDED == "embedded"
        assert ProcessingStage.INDEXED == "indexed"

    def test_processing_statuses(self):
        """Test ProcessingStatus constants."""
        assert ProcessingStatus.PENDING == "pending"
        assert ProcessingStatus.COMPLETED == "completed"
        assert ProcessingStatus.FAILED == "failed"


# ============================================================================
# Edge Cases and Validation Tests
# ============================================================================

@pytest.mark.unit
class TestModelEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_document_with_empty_metadata(self):
        """Test document with empty metadata."""
        doc = Document(filename="test.pdf", metadata={})
        assert doc.metadata == {}
        doc.update_metadata(key="value")
        assert doc.metadata == {"key": "value"}

    def test_document_with_null_metadata_in_db_row(self):
        """Test handling None metadata from database."""
        row = (1, "test.pdf", None, None, None, None, None, None)
        doc = Document.from_db_row(row)
        assert doc.metadata == {}  # Converted to empty dict

    def test_clause_with_zero_confidence(self):
        """Test clause with zero confidence score."""
        clause = Clause(
            document_id=1,
            clause_text="Low confidence clause",
            confidence_score=0.0
        )
        assert clause.confidence_score == 0.0

    def test_clause_with_partial_bbox(self):
        """Test clause with partial bounding box data."""
        clause = Clause(
            document_id=1,
            clause_text="test",
            bbox_x=10.0,
            bbox_y=20.0,
            # Missing width and height
        )
        assert clause.has_bounding_box() is False
        assert clause.get_bounding_box() is None

    def test_processing_log_with_error_message(self):
        """Test processing log with error message."""
        log = ProcessingLog(
            document_id=1,
            processing_stage=ProcessingStage.EXTRACTED,
            status=ProcessingStatus.FAILED,
            error_message="Connection timeout during extraction"
        )
        assert log.is_failed() is True
        assert "timeout" in log.error_message.lower()

    def test_document_hash_with_large_data(self):
        """Test hash computation with large binary data."""
        large_data = b"x" * (10 * 1024 * 1024)  # 10 MB
        hash_value = Document.compute_hash(large_data)
        assert len(hash_value) == 64
        assert hash_value.isalnum()
