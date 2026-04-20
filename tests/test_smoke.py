"""
Quick smoke tests for CI/CD pipelines.

These are fast tests that verify basic functionality.
Run with: pytest tests/test_smoke.py -m smoke

Note: These tests only require the contractex.storage module - no database connection needed.
"""

from __future__ import annotations

import pytest


@pytest.mark.smoke
@pytest.mark.unit
class TestSmoke:
    """Quick smoke tests."""

    def test_model_imports(self):
        """Test that model classes can be imported."""
        from contractex.storage.models import Clause, Document, ProcessingLog

        assert Document is not None
        assert Clause is not None
        assert ProcessingLog is not None

    def test_document_creation(self):
        """Test basic Document instantiation."""
        from contractex.storage.models import Document

        doc = Document(filename="test.pdf")
        assert doc.filename == "test.pdf"
        assert doc.id is None
        assert doc.metadata == {}

    def test_clause_creation(self):
        """Test basic Clause instantiation."""
        from contractex.storage.models import Clause

        clause = Clause(document_id=1, clause_text="test clause")
        assert clause.clause_text == "test clause"
        assert clause.document_id == 1

    def test_processing_log_creation(self):
        """Test basic ProcessingLog instantiation."""
        from contractex.storage.models import ProcessingLog

        log = ProcessingLog(document_id=1, processing_stage="uploaded", status="completed")
        assert log.status == "completed"
        assert log.processing_stage == "uploaded"

    def test_config_module(self):
        """Test that configuration module loads."""
        from contractex.storage.config import get_db_config

        config = get_db_config()
        assert "host" in config
        assert "db_name" in config
        assert "user" in config

    def test_document_hash(self):
        """Test document hash computation."""
        from contractex.storage.models import Document

        hash_val = Document.compute_hash(b"test data")
        assert len(hash_val) == 64
        assert hash_val.isalnum()

        # Test deterministic hashing
        hash_val2 = Document.compute_hash(b"test data")
        assert hash_val == hash_val2

    def test_controlled_vocabularies(self):
        """Test controlled vocabulary constants."""
        from contractex.storage.models import ClauseType, ProcessingStage, ProcessingStatus

        assert ClauseType.PAYMENT == "payment"
        assert ProcessingStage.UPLOADED == "uploaded"
        assert ProcessingStatus.COMPLETED == "completed"

    def test_clause_bounding_box(self):
        """Test clause bounding box functionality."""
        from contractex.storage.models import Clause

        clause = Clause(
            document_id=1,
            clause_text="test",
            bbox_x=10.0,
            bbox_y=20.0,
            bbox_width=100.0,
            bbox_height=50.0,
        )

        assert clause.has_bounding_box() is True
        bbox = clause.get_bounding_box()
        assert bbox is not None
        assert bbox["x"] == 10.0
        assert bbox["height"] == 50.0
