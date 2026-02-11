"""
Repository pattern implementation for database operations.

Each repository class encapsulates all database operations for a domain model,
providing a clean API that hides SQL details from application code.
This makes the codebase testable (mock repositories) and database-agnostic.
"""
import logging
from typing import Any, Optional

import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values

from contractex.storage.connection import get_cursor
from contractex.storage.models import Clause, Document, ProcessingLog

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Repository for Document database operations."""

    def __init__(self, connection=None):
        """
        Initialize repository.

        Args:
            connection: Optional psycopg2 connection. If None, uses context managers.
        """
        self.connection = connection

    def insert(self, doc: Document) -> int:
        """
        Insert a new document.

        Args:
            doc: Document object to insert

        Returns:
            ID of the inserted document
        """
        query = """
            INSERT INTO documents (filename, file_hash, file_data, extracted_text, metadata)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (filename) DO NOTHING
            RETURNING id
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (
                    doc.filename,
                    doc.file_hash,
                    doc.file_data,
                    doc.extracted_text,
                    psycopg2.extras.Json(doc.metadata)
                ))
                result = cur.fetchone()
                if result:
                    doc_id = result[0]
                    logger.info(f"Inserted document: {doc.filename} (ID: {doc_id})")
                    return doc_id
                else:
                    logger.warning(f"Document already exists: {doc.filename}")
                    return self.get_id_by_filename(doc.filename)
        except Exception as e:
            logger.error(f"Failed to insert document: {e}")
            raise

    def get_by_id(self, doc_id: int) -> Optional[Document]:
        """
        Retrieve document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document object or None if not found
        """
        query = """
            SELECT id, filename, file_hash, file_data, extracted_text,
                   metadata, uploaded_at, updated_at
            FROM documents
            WHERE id = %s
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (doc_id,))
                row = cur.fetchone()
                if row:
                    return Document.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve document {doc_id}: {e}")
            raise

    def get_by_filename(self, filename: str) -> Optional[Document]:
        """Retrieve document by filename."""
        query = """
            SELECT id, filename, file_hash, file_data, extracted_text,
                   metadata, uploaded_at, updated_at
            FROM documents
            WHERE filename = %s
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (filename,))
                row = cur.fetchone()
                if row:
                    return Document.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve document by filename: {e}")
            raise

    def get_id_by_filename(self, filename: str) -> Optional[int]:
        """Get document ID by filename."""
        query = "SELECT id FROM documents WHERE filename = %s"
        try:
            with get_cursor() as cur:
                cur.execute(query, (filename,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to get document ID: {e}")
            raise

    def search_by_metadata(self, filters: dict[str, Any]) -> list[Document]:
        """
        Search documents by metadata fields.

        Args:
            filters: Dict of metadata field filters (e.g., {'contract_type': 'NDA'})

        Returns:
            List of matching Document objects
        """
        conditions = []
        params = []

        for key, value in filters.items():
            conditions.append("metadata->>%s = %s")
            params.extend([key, value])

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, filename, file_hash, file_data, extracted_text,
                   metadata, uploaded_at, updated_at
            FROM documents
            WHERE {where_clause}
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                return [Document.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to search documents: {e}")
            raise

    def get_all(self, limit: Optional[int] = None) -> list[Document]:
        """
        Retrieve all documents.

        Args:
            limit: Optional limit on number of results

        Returns:
            List of Document objects
        """
        query = """
            SELECT id, filename, file_hash, file_data, extracted_text,
                   metadata, uploaded_at, updated_at
            FROM documents
            ORDER BY uploaded_at DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        try:
            with get_cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [Document.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve all documents: {e}")
            raise

    def update_extracted_text(self, doc_id: int, extracted_text: str) -> None:
        """Update extracted text for a document."""
        query = """
            UPDATE documents
            SET extracted_text = %s, updated_at = NOW()
            WHERE id = %s
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (extracted_text, doc_id))
                logger.info(f"Updated extracted text for document {doc_id}")
        except Exception as e:
            logger.error(f"Failed to update extracted text: {e}")
            raise

    def update_metadata(self, doc_id: int, metadata: dict[str, Any]) -> None:
        """Update metadata for a document."""
        query = """
            UPDATE documents
            SET metadata = %s, updated_at = NOW()
            WHERE id = %s
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (psycopg2.extras.Json(metadata), doc_id))
                logger.info(f"Updated metadata for document {doc_id}")
        except Exception as e:
            logger.error(f"Failed to update metadata: {e}")
            raise

    def delete(self, doc_id: int) -> None:
        """Delete a document (cascades to clauses)."""
        query = "DELETE FROM documents WHERE id = %s"

        try:
            with get_cursor() as cur:
                cur.execute(query, (doc_id,))
                logger.info(f"Deleted document {doc_id}")
        except Exception as e:
            logger.error(f"Failed to delete document: {e}")
            raise

    def count(self) -> int:
        """Count total documents."""
        query = "SELECT COUNT(*) FROM documents"
        try:
            with get_cursor() as cur:
                cur.execute(query)
                result = cur.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Failed to count documents: {e}")
            raise


class ClauseRepository:
    """Repository for Clause database operations."""

    def __init__(self, connection=None):
        """Initialize repository."""
        self.connection = connection

    def insert(self, clause: Clause) -> int:
        """Insert a single clause."""
        query = """
            INSERT INTO clauses (
                document_id, clause_text, clause_type, page_number,
                bbox_x, bbox_y, bbox_width, bbox_height,
                confidence_score, parent_clause_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (
                    clause.document_id,
                    clause.clause_text,
                    clause.clause_type,
                    clause.page_number,
                    clause.bbox_x,
                    clause.bbox_y,
                    clause.bbox_width,
                    clause.bbox_height,
                    clause.confidence_score,
                    clause.parent_clause_id,
                    psycopg2.extras.Json(clause.metadata)
                ))
                result = cur.fetchone()
                clause_id = result[0] if result else 0
                logger.debug(f"Inserted clause {clause_id} for document {clause.document_id}")
                return clause_id
        except Exception as e:
            logger.error(f"Failed to insert clause: {e}")
            raise

    def insert_batch(self, clauses: list[Clause]) -> list[int]:
        """
        Bulk insert clauses.

        Args:
            clauses: List of Clause objects

        Returns:
            List of inserted clause IDs
        """
        if not clauses:
            return []

        query = """
            INSERT INTO clauses (
                document_id, clause_text, clause_type, page_number,
                bbox_x, bbox_y, bbox_width, bbox_height,
                confidence_score, parent_clause_id, metadata
            )
            VALUES %s
            RETURNING id
        """

        values = [
            (
                c.document_id, c.clause_text, c.clause_type, c.page_number,
                c.bbox_x, c.bbox_y, c.bbox_width, c.bbox_height,
                c.confidence_score, c.parent_clause_id,
                psycopg2.extras.Json(c.metadata)
            )
            for c in clauses
        ]

        try:
            with get_cursor() as cur:
                ids = execute_values(cur, query, values, fetch=True)
                clause_ids = [row[0] for row in ids]
                logger.info(f"Inserted {len(clause_ids)} clauses")
                return clause_ids
        except Exception as e:
            logger.error(f"Failed to batch insert clauses: {e}")
            raise

    def get_by_id(self, clause_id: int) -> Optional[Clause]:
        """Retrieve clause by ID."""
        query = """
            SELECT id, document_id, clause_text, clause_type, page_number,
                   bbox_x, bbox_y, bbox_width, bbox_height,
                   confidence_score, parent_clause_id, metadata, created_at
            FROM clauses
            WHERE id = %s
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (clause_id,))
                row = cur.fetchone()
                if row:
                    return Clause.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve clause: {e}")
            raise

    def get_by_document(self, document_id: int) -> list[Clause]:
        """Get all clauses for a document."""
        query = """
            SELECT id, document_id, clause_text, clause_type, page_number,
                   bbox_x, bbox_y, bbox_width, bbox_height,
                   confidence_score, parent_clause_id, metadata, created_at
            FROM clauses
            WHERE document_id = %s
            ORDER BY page_number, id
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (document_id,))
                rows = cur.fetchall()
                return [Clause.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve clauses for document: {e}")
            raise

    def search_by_type(self, clause_type: str, limit: Optional[int] = None) -> list[Clause]:
        """Search clauses by type across all documents."""
        query = """
            SELECT id, document_id, clause_text, clause_type, page_number,
                   bbox_x, bbox_y, bbox_width, bbox_height,
                   confidence_score, parent_clause_id, metadata, created_at
            FROM clauses
            WHERE clause_type = %s
            ORDER BY created_at DESC
        """

        if limit:
            query += f" LIMIT {limit}"

        try:
            with get_cursor() as cur:
                cur.execute(query, (clause_type,))
                rows = cur.fetchall()
                return [Clause.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to search clauses by type: {e}")
            raise

    def delete_by_document(self, document_id: int) -> None:
        """Delete all clauses for a document."""
        query = "DELETE FROM clauses WHERE document_id = %s"

        try:
            with get_cursor() as cur:
                cur.execute(query, (document_id,))
                logger.info(f"Deleted clauses for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete clauses: {e}")
            raise

    def count_by_document(self, document_id: int) -> int:
        """Count clauses for a document."""
        query = "SELECT COUNT(*) FROM clauses WHERE document_id = %s"
        try:
            with get_cursor() as cur:
                cur.execute(query, (document_id,))
                result = cur.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Failed to count clauses: {e}")
            raise


class ProcessingLogRepository:
    """Repository for ProcessingLog database operations."""

    def __init__(self, connection=None):
        """Initialize repository."""
        self.connection = connection

    def insert(self, log: ProcessingLog) -> int:
        """Insert a processing log entry."""
        query = """
            INSERT INTO processing_log (
                document_id, processing_stage, status, error_message
            )
            VALUES (%s, %s, %s, %s)
            RETURNING id
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (
                    log.document_id,
                    log.processing_stage,
                    log.status,
                    log.error_message
                ))
                result = cur.fetchone()
                log_id = result[0] if result else 0
                logger.debug(f"Inserted processing log {log_id}")
                return log_id
        except Exception as e:
            logger.error(f"Failed to insert processing log: {e}")
            raise

    def get_by_document(self, document_id: int) -> list[ProcessingLog]:
        """Get all processing logs for a document."""
        query = """
            SELECT id, document_id, processing_stage, status, error_message, created_at
            FROM processing_log
            WHERE document_id = %s
            ORDER BY created_at DESC
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (document_id,))
                rows = cur.fetchall()
                return [ProcessingLog.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve processing logs: {e}")
            raise

    def get_failed_documents(self) -> list[int]:
        """Get IDs of documents with failed processing."""
        query = """
            SELECT DISTINCT document_id
            FROM processing_log
            WHERE status = 'failed'
            ORDER BY document_id
        """

        try:
            with get_cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve failed documents: {e}")
            raise

    def get_latest_by_stage(self, document_id: int, stage: str) -> Optional[ProcessingLog]:
        """Get most recent log entry for a document and stage."""
        query = """
            SELECT id, document_id, processing_stage, status, error_message, created_at
            FROM processing_log
            WHERE document_id = %s AND processing_stage = %s
            ORDER BY created_at DESC
            LIMIT 1
        """

        try:
            with get_cursor() as cur:
                cur.execute(query, (document_id, stage))
                row = cur.fetchone()
                if row:
                    return ProcessingLog.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve latest log: {e}")
            raise
