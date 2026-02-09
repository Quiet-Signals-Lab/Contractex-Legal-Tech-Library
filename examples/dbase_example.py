"""
Example usage of the database layer for legal document analysis.

This script demonstrates:
1. Document insertion with metadata
2. Clause extraction and storage
3. Querying and searching
4. Processing log tracking

Run after database setup:
    python examples/dbase_example.py
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dbase import (
    DocumentRepository,
    ClauseRepository,
    ProcessingLogRepository,
    Document,
    Clause,
    ProcessingLog,
    ClauseType,
    ProcessingStage,
    ProcessingStatus
)
from dbase.connection import test_connection
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def example_document_operations():
    """Example: Document CRUD operations."""
    logger.info("=" * 70)
    logger.info("Example 1: Document Operations")
    logger.info("=" * 70)
    
    # Initialize repository
    doc_repo = DocumentRepository()
    
    # Create a document
    doc = Document(
        filename="example_nda_2024.pdf",
        file_hash=Document.compute_hash(b"example binary data"),
        extracted_text="This Non-Disclosure Agreement is entered into...",
        metadata={
            "contract_type": "NDA",
            "parties": ["Acme Corporation", "Beta Industries"],
            "effective_date": "2024-01-15",
            "expiration_date": "2026-01-15",
            "governing_law": "Delaware",
            "custom_tags": ["vendor", "confidentiality"]
        }
    )
    
    # Insert document
    doc_id = doc_repo.insert(doc)
    logger.info(f"Inserted document with ID: {doc_id}")
    
    # Retrieve by ID
    retrieved = doc_repo.get_by_id(doc_id)
    logger.info(f"Retrieved: {retrieved.filename}")
    logger.info(f"Metadata: {retrieved.metadata}")
    
    # Search by metadata
    ndas = doc_repo.search_by_metadata({"contract_type": "NDA"})
    logger.info(f"Found {len(ndas)} NDA documents")
    
    # Update metadata
    doc_repo.update_metadata(doc_id, {
        **retrieved.metadata,
        "reviewed": True,
        "reviewer": "Legal Team"
    })
    logger.info("Updated metadata")
    
    return doc_id


def example_clause_operations(document_id):
    """Example: Clause extraction and storage."""
    logger.info("\n" + "=" * 70)
    logger.info("Example 2: Clause Operations")
    logger.info("=" * 70)
    
    clause_repo = ClauseRepository()
    
    # Create multiple clauses
    clauses = [
        Clause(
            document_id=document_id,
            clause_text="Each party agrees to maintain confidential information in strict confidence.",
            clause_type=ClauseType.CONFIDENTIALITY,
            page_number=1,
            bbox_x=50.0,
            bbox_y=200.0,
            bbox_width=500.0,
            bbox_height=50.0,
            confidence_score=0.98
        ),
        Clause(
            document_id=document_id,
            clause_text="Party A shall pay Party B $10,000 within 30 days of invoice.",
            clause_type=ClauseType.PAYMENT,
            page_number=3,
            confidence_score=0.95,
            metadata={"amount": 10000, "currency": "USD", "payment_term": 30}
        ),
        Clause(
            document_id=document_id,
            clause_text="This agreement may be terminated by either party with 30 days written notice.",
            clause_type=ClauseType.TERMINATION,
            page_number=5,
            confidence_score=0.92
        ),
        Clause(
            document_id=document_id,
            clause_text="Neither party shall be liable for acts of God or force majeure events.",
            clause_type=ClauseType.FORCE_MAJEURE,
            page_number=6,
            confidence_score=0.89
        )
    ]
    
    # Batch insert clauses
    clause_ids = clause_repo.insert_batch(clauses)
    logger.info(f"Inserted {len(clause_ids)} clauses")
    
    # Get all clauses for document
    doc_clauses = clause_repo.get_by_document(document_id)
    logger.info(f"Document has {len(doc_clauses)} clauses")
    
    for clause in doc_clauses:
        logger.info(f"  - {clause.clause_type}: {clause.clause_text[:60]}...")
        if clause.has_bounding_box():
            logger.info(f"    Bounding box: {clause.get_bounding_box()}")
    
    # Search by clause type
    payment_clauses = clause_repo.search_by_type(ClauseType.PAYMENT)
    logger.info(f"Found {len(payment_clauses)} payment clauses across all documents")
    
    return clause_ids


def example_processing_log(document_id):
    """Example: Processing log tracking."""
    logger.info("\n" + "=" * 70)
    logger.info("Example 3: Processing Log Tracking")
    logger.info("=" * 70)
    
    log_repo = ProcessingLogRepository()
    
    # Track processing stages
    stages = [
        (ProcessingStage.UPLOADED, ProcessingStatus.COMPLETED, None),
        (ProcessingStage.EXTRACTED, ProcessingStatus.COMPLETED, None),
        (ProcessingStage.INDEXED, ProcessingStatus.COMPLETED, None),
    ]
    
    for stage, status, error in stages:
        log = ProcessingLog(
            document_id=document_id,
            processing_stage=stage,
            status=status,
            error_message=error
        )
        log_repo.insert(log)
        logger.info(f"Logged: {stage} - {status}")
    
    # Retrieve processing history
    logs = log_repo.get_by_document(document_id)
    logger.info(f"\nProcessing history for document {document_id}:")
    for log in logs:
        status_icon = "✓" if log.is_completed() else "✗"
        logger.info(f"  {status_icon} {log.processing_stage}: {log.status} at {log.created_at}")


def example_advanced_queries():
    """Example: Advanced query patterns."""
    logger.info("\n" + "=" * 70)
    logger.info("Example 4: Advanced Queries")
    logger.info("=" * 70)
    
    doc_repo = DocumentRepository()
    clause_repo = ClauseRepository()
    
    # Get all documents
    all_docs = doc_repo.get_all(limit=5)
    logger.info(f"Total documents (limited to 5): {len(all_docs)}")
    
    for doc in all_docs:
        clause_count = clause_repo.count_by_document(doc.id)
        contract_type = doc.get_metadata_field("contract_type", "Unknown")
        logger.info(f"  {doc.filename}: {clause_count} clauses, type: {contract_type}")
    
    # Document statistics
    total_docs = doc_repo.count()
    logger.info(f"\nTotal documents in database: {total_docs}")
    
    # Find documents by multiple metadata fields
    # (Would need to extend search_by_metadata for complex AND conditions)
    logger.info("\nMetadata search capabilities enabled via JSONB indexes")


def main():
    """Run all examples."""
    # Check database connection
    if not test_connection():
        logger.error("Database connection failed! Run 'python -m dbase.setup' first.")
        sys.exit(1)
    
    logger.info("Database connection successful!\n")
    
    try:
        # Example 1: Document operations
        doc_id = example_document_operations()
        
        # Example 2: Clause operations
        clause_ids = example_clause_operations(doc_id)
        
        # Example 3: Processing log
        example_processing_log(doc_id)
        
        # Example 4: Advanced queries
        example_advanced_queries()
        
        logger.info("\n" + "=" * 70)
        logger.info("All examples completed successfully!")
        logger.info("=" * 70)
        
    except Exception as e:
        logger.error(f"Example failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
