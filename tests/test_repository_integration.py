"""
Integration tests for database repositories.

These tests require a real PostgreSQL database connection and test
the full stack from repository through to database.
"""
import pytest
from contractex.storage.models import (
    Document, Clause, ProcessingLog,
    ClauseType, ProcessingStage, ProcessingStatus
)


# ============================================================================
# DocumentRepository Integration Tests
# ============================================================================

@pytest.mark.integration
class TestDocumentRepositoryIntegration:
    """Test DocumentRepository with real database."""
    
    def test_insert_document(self, doc_repo, sample_document):
        """Test inserting a document."""
        doc_id = doc_repo.insert(sample_document)
        
        assert doc_id > 0
        assert isinstance(doc_id, int)
    
    def test_insert_duplicate_filename(self, doc_repo, sample_document):
        """Test inserting document with duplicate filename."""
        doc_id1 = doc_repo.insert(sample_document)
        doc_id2 = doc_repo.insert(sample_document)  # Same filename
        
        # Should return existing ID, not create new
        assert doc_id1 == doc_id2
    
    def test_get_by_id(self, doc_repo, sample_document):
        """Test retrieving document by ID."""
        doc_id = doc_repo.insert(sample_document)
        retrieved = doc_repo.get_by_id(doc_id)
        
        assert retrieved is not None
        assert retrieved.id == doc_id
        assert retrieved.filename == sample_document.filename
        assert retrieved.metadata["contract_type"] == "NDA"
    
    def test_get_by_id_nonexistent(self, doc_repo):
        """Test retrieving non-existent document."""
        result = doc_repo.get_by_id(99999)
        assert result is None
    
    def test_get_by_filename(self, doc_repo, sample_document):
        """Test retrieving document by filename."""
        doc_repo.insert(sample_document)
        retrieved = doc_repo.get_by_filename(sample_document.filename)
        
        assert retrieved is not None
        assert retrieved.filename == sample_document.filename
    
    def test_search_by_metadata(self, doc_repo, multiple_documents):
        """Test searching documents by metadata."""
        # Insert multiple documents
        for doc in multiple_documents:
            doc_repo.insert(doc)
        
        # Search for NDAs
        ndas = doc_repo.search_by_metadata({"contract_type": "NDA"})
        assert len(ndas) == 3  # Documents with even indices
        
        for doc in ndas:
            assert doc.metadata["contract_type"] == "NDA"
    
    def test_get_all(self, doc_repo, multiple_documents):
        """Test retrieving all documents."""
        for doc in multiple_documents:
            doc_repo.insert(doc)
        
        all_docs = doc_repo.get_all()
        assert len(all_docs) == len(multiple_documents)
    
    def test_get_all_with_limit(self, doc_repo, multiple_documents):
        """Test retrieving documents with limit."""
        for doc in multiple_documents:
            doc_repo.insert(doc)
        
        limited = doc_repo.get_all(limit=3)
        assert len(limited) == 3
    
    def test_update_extracted_text(self, doc_repo, sample_document):
        """Test updating extracted text."""
        doc_id = doc_repo.insert(sample_document)
        
        new_text = "Updated extracted text content"
        doc_repo.update_extracted_text(doc_id, new_text)
        
        retrieved = doc_repo.get_by_id(doc_id)
        assert retrieved.extracted_text == new_text
    
    def test_update_metadata(self, doc_repo, sample_document):
        """Test updating metadata."""
        doc_id = doc_repo.insert(sample_document)
        
        new_metadata = {
            **sample_document.metadata,
            "reviewed": True,
            "reviewer": "Jane Doe"
        }
        doc_repo.update_metadata(doc_id, new_metadata)
        
        retrieved = doc_repo.get_by_id(doc_id)
        assert retrieved.metadata["reviewed"] is True
        assert retrieved.metadata["reviewer"] == "Jane Doe"
    
    def test_delete_document(self, doc_repo, sample_document):
        """Test deleting a document."""
        doc_id = doc_repo.insert(sample_document)
        
        # Verify exists
        assert doc_repo.get_by_id(doc_id) is not None
        
        # Delete
        doc_repo.delete(doc_id)
        
        # Verify deleted
        assert doc_repo.get_by_id(doc_id) is None
    
    def test_count(self, doc_repo, multiple_documents):
        """Test counting documents."""
        assert doc_repo.count() == 0
        
        for doc in multiple_documents:
            doc_repo.insert(doc)
        
        assert doc_repo.count() == len(multiple_documents)


# ============================================================================
# ClauseRepository Integration Tests
# ============================================================================

@pytest.mark.integration
class TestClauseRepositoryIntegration:
    """Test ClauseRepository with real database."""
    
    def test_insert_clause(self, doc_repo, clause_repo, sample_document, sample_clause):
        """Test inserting a clause."""
        doc_id = doc_repo.insert(sample_document)
        sample_clause.document_id = doc_id
        
        clause_id = clause_repo.insert(sample_clause)
        
        assert clause_id > 0
        assert isinstance(clause_id, int)
    
    def test_insert_batch(self, doc_repo, clause_repo, sample_document, multiple_clauses):
        """Test batch inserting clauses."""
        doc_id = doc_repo.insert(sample_document)
        
        # Set all clauses to same document
        for clause in multiple_clauses:
            clause.document_id = doc_id
        
        clause_ids = clause_repo.insert_batch(multiple_clauses)
        
        assert len(clause_ids) == len(multiple_clauses)
        assert all(isinstance(cid, int) for cid in clause_ids)
    
    def test_insert_batch_empty(self, clause_repo):
        """Test batch insert with empty list."""
        result = clause_repo.insert_batch([])
        assert result == []
    
    def test_get_by_id(self, doc_repo, clause_repo, sample_document, sample_clause):
        """Test retrieving clause by ID."""
        doc_id = doc_repo.insert(sample_document)
        sample_clause.document_id = doc_id
        
        clause_id = clause_repo.insert(sample_clause)
        retrieved = clause_repo.get_by_id(clause_id)
        
        assert retrieved is not None
        assert retrieved.id == clause_id
        assert retrieved.clause_text == sample_clause.clause_text
        assert retrieved.clause_type == sample_clause.clause_type
    
    def test_get_by_document(self, doc_repo, clause_repo, sample_document, multiple_clauses):
        """Test retrieving all clauses for a document."""
        doc_id = doc_repo.insert(sample_document)
        
        for clause in multiple_clauses:
            clause.document_id = doc_id
        clause_repo.insert_batch(multiple_clauses)
        
        clauses = clause_repo.get_by_document(doc_id)
        
        assert len(clauses) == len(multiple_clauses)
        assert all(c.document_id == doc_id for c in clauses)
    
    def test_search_by_type(self, doc_repo, clause_repo, sample_document, multiple_clauses):
        """Test searching clauses by type."""
        doc_id = doc_repo.insert(sample_document)
        
        for clause in multiple_clauses:
            clause.document_id = doc_id
        clause_repo.insert_batch(multiple_clauses)
        
        payment_clauses = clause_repo.search_by_type("payment")
        
        assert len(payment_clauses) > 0
        assert all(c.clause_type == "payment" for c in payment_clauses)
    
    def test_search_by_type_with_limit(self, doc_repo, clause_repo, sample_document, multiple_clauses):
        """Test searching clauses by type with limit."""
        doc_id = doc_repo.insert(sample_document)
        
        for clause in multiple_clauses:
            clause.document_id = doc_id
        clause_repo.insert_batch(multiple_clauses)
        
        limited = clause_repo.search_by_type("payment", limit=1)
        assert len(limited) == 1
    
    def test_delete_by_document(self, doc_repo, clause_repo, sample_document, multiple_clauses):
        """Test deleting all clauses for a document."""
        doc_id = doc_repo.insert(sample_document)
        
        for clause in multiple_clauses:
            clause.document_id = doc_id
        clause_repo.insert_batch(multiple_clauses)
        
        # Verify clauses exist
        assert len(clause_repo.get_by_document(doc_id)) > 0
        
        # Delete
        clause_repo.delete_by_document(doc_id)
        
        # Verify deleted
        assert len(clause_repo.get_by_document(doc_id)) == 0
    
    def test_count_by_document(self, doc_repo, clause_repo, sample_document, multiple_clauses):
        """Test counting clauses for a document."""
        doc_id = doc_repo.insert(sample_document)
        
        assert clause_repo.count_by_document(doc_id) == 0
        
        for clause in multiple_clauses:
            clause.document_id = doc_id
        clause_repo.insert_batch(multiple_clauses)
        
        assert clause_repo.count_by_document(doc_id) == len(multiple_clauses)
    
    def test_cascade_delete(self, doc_repo, clause_repo, sample_document, multiple_clauses):
        """Test that deleting document cascades to clauses."""
        doc_id = doc_repo.insert(sample_document)
        
        for clause in multiple_clauses:
            clause.document_id = doc_id
        clause_repo.insert_batch(multiple_clauses)
        
        # Verify clauses exist
        assert clause_repo.count_by_document(doc_id) > 0
        
        # Delete document
        doc_repo.delete(doc_id)
        
        # Verify clauses also deleted (cascade)
        assert clause_repo.count_by_document(doc_id) == 0


# ============================================================================
# ProcessingLogRepository Integration Tests
# ============================================================================

@pytest.mark.integration
class TestProcessingLogRepositoryIntegration:
    """Test ProcessingLogRepository with real database."""
    
    def test_insert_log(self, doc_repo, log_repo, sample_document, sample_processing_log):
        """Test inserting a processing log."""
        doc_id = doc_repo.insert(sample_document)
        sample_processing_log.document_id = doc_id
        
        log_id = log_repo.insert(sample_processing_log)
        
        assert log_id > 0
        assert isinstance(log_id, int)
    
    def test_get_by_document(self, doc_repo, log_repo, sample_document):
        """Test retrieving processing logs for a document."""
        doc_id = doc_repo.insert(sample_document)
        
        # Insert multiple log entries
        stages = [
            (ProcessingStage.UPLOADED, ProcessingStatus.COMPLETED),
            (ProcessingStage.EXTRACTED, ProcessingStatus.COMPLETED),
            (ProcessingStage.INDEXED, ProcessingStatus.PENDING),
        ]
        
        for stage, status in stages:
            log = ProcessingLog(
                document_id=doc_id,
                processing_stage=stage,
                status=status
            )
            log_repo.insert(log)
        
        logs = log_repo.get_by_document(doc_id)
        
        assert len(logs) == len(stages)
        # Should be ordered by created_at DESC
        assert logs[0].processing_stage == ProcessingStage.INDEXED
    
    def test_get_failed_documents(self, doc_repo, log_repo, multiple_documents):
        """Test retrieving failed documents."""
        # Insert documents with mixed statuses
        for i, doc in enumerate(multiple_documents):
            doc_id = doc_repo.insert(doc)
            
            status = ProcessingStatus.FAILED if i % 2 == 0 else ProcessingStatus.COMPLETED
            log = ProcessingLog(
                document_id=doc_id,
                processing_stage=ProcessingStage.EXTRACTED,
                status=status,
                error_message="Error" if status == ProcessingStatus.FAILED else None
            )
            log_repo.insert(log)
        
        failed_ids = log_repo.get_failed_documents()
        
        assert len(failed_ids) == 3  # Documents with even indices
        assert all(isinstance(doc_id, int) for doc_id in failed_ids)
    
    def test_get_latest_by_stage(self, doc_repo, log_repo, sample_document):
        """Test retrieving latest log for a stage."""
        doc_id = doc_repo.insert(sample_document)
        
        # Insert multiple logs for same stage
        for status in [ProcessingStatus.PENDING, ProcessingStatus.COMPLETED]:
            log = ProcessingLog(
                document_id=doc_id,
                processing_stage=ProcessingStage.EXTRACTED,
                status=status
            )
            log_repo.insert(log)
        
        latest = log_repo.get_latest_by_stage(doc_id, ProcessingStage.EXTRACTED)
        
        assert latest is not None
        assert latest.status == ProcessingStatus.COMPLETED  # Latest
    
    def test_get_latest_by_stage_nonexistent(self, log_repo):
        """Test retrieving latest log for non-existent document/stage."""
        result = log_repo.get_latest_by_stage(99999, ProcessingStage.UPLOADED)
        assert result is None


# ============================================================================
# Cross-Repository Integration Tests
# ============================================================================

@pytest.mark.integration
class TestCrossRepositoryIntegration:
    """Test interactions between multiple repositories."""
    
    def test_full_document_workflow(self, doc_repo, clause_repo, log_repo):
        """Test complete document processing workflow."""
        # 1. Insert document
        doc = Document(
            filename="workflow_test.pdf",
            extracted_text="Contract text...",
            metadata={"contract_type": "MSA"}
        )
        doc_id = doc_repo.insert(doc)
        
        # 2. Log upload
        log_repo.insert(ProcessingLog(
            document_id=doc_id,
            processing_stage=ProcessingStage.UPLOADED,
            status=ProcessingStatus.COMPLETED
        ))
        
        # 3. Extract clauses
        clauses = [
            Clause(
                document_id=doc_id,
                clause_text=f"Clause {i}",
                clause_type="payment" if i % 2 == 0 else "termination"
            )
            for i in range(5)
        ]
        clause_ids = clause_repo.insert_batch(clauses)
        
        # 4. Log extraction
        log_repo.insert(ProcessingLog(
            document_id=doc_id,
            processing_stage=ProcessingStage.EXTRACTED,
            status=ProcessingStatus.COMPLETED
        ))
        
        # Verify everything
        assert doc_repo.get_by_id(doc_id) is not None
        assert len(clause_repo.get_by_document(doc_id)) == 5
        assert len(log_repo.get_by_document(doc_id)) == 2
    
    def test_document_deletion_cascades(self, doc_repo, clause_repo, log_repo):
        """Test that document deletion cascades to related records."""
        # Setup data
        doc = Document(filename="cascade_test.pdf")
        doc_id = doc_repo.insert(doc)
        
        clause_repo.insert(Clause(document_id=doc_id, clause_text="Test"))
        log_repo.insert(ProcessingLog(
            document_id=doc_id,
            processing_stage=ProcessingStage.UPLOADED,
            status=ProcessingStatus.COMPLETED
        ))
        
        # Delete document
        doc_repo.delete(doc_id)
        
        # Verify cascading deletes
        assert clause_repo.count_by_document(doc_id) == 0
        assert len(log_repo.get_by_document(doc_id)) == 0
