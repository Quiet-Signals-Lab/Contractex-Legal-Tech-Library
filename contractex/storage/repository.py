"""
Repository pattern implementation for database operations.

Each repository class encapsulates all database operations for a domain model,
providing a clean API that hides SQL details from application code.
This makes the codebase testable (mock repositories) and database-agnostic.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import psycopg2
import psycopg2.errors
import psycopg2.extras
from psycopg2.extras import execute_values

from contractex.exceptions import ContractExError
from contractex.storage.connection import (
    error_summary,
    get_cursor,
    get_vector_cursor,
    register_vector_types,
)
from contractex.storage.models import Clause, Document, ProcessingLog

logger = logging.getLogger(__name__)

_NO_EMBEDDING_COLUMN = (
    "clauses.embedding does not exist. Apply "
    "contractex/storage/migrations/add_embeddings.sql (needs the pgvector extension)."
)


class DuplicateDocumentError(ContractExError):
    """Raised when a different document is already stored under the same filename."""


class DocumentNotFoundError(ContractExError):
    """Raised when the document to update does not exist."""


class _Repository:
    """Cursor handling shared by the repositories."""

    def __init__(self, connection: Any = None) -> None:
        """
        Initialize repository.

        Args:
            connection: Optional psycopg2 connection.  When given, every
                operation runs on it and the caller commits or rolls back, so
                several operations can share one transaction.  If None, each
                operation opens its own connection and commits.
        """
        self.connection = connection

    @contextmanager
    def _cursor(self, vector: bool = False) -> Iterator[Any]:
        if self.connection is None:
            with get_vector_cursor() if vector else get_cursor() as cur:
                yield cur
            return
        if vector:
            register_vector_types(self.connection)
        cur = self.connection.cursor()
        try:
            yield cur
        finally:
            cur.close()


class DocumentRepository(_Repository):
    """Repository for Document database operations."""

    def insert(self, doc: Document) -> int:
        """
        Insert a new document.

        Args:
            doc: Document object to insert

        Returns:
            ID of the inserted document, or of the stored one when this same
            document (same hash, or same text when a hash is missing) is
            inserted again

        Raises:
            DuplicateDocumentError: If a different document is already stored
                under this filename
        """
        query = """
            INSERT INTO documents (filename, file_hash, file_data, extracted_text, metadata)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (filename) DO NOTHING
            RETURNING id
        """

        try:
            with self._cursor() as cur:
                cur.execute(
                    query,
                    (
                        doc.filename,
                        doc.file_hash,
                        doc.file_data,
                        doc.extracted_text,
                        psycopg2.extras.Json(doc.metadata),
                    ),
                )
                result = cur.fetchone()
                if result:
                    doc_id: int = result[0]
                    logger.info(f"Inserted document: {doc.filename} (ID: {doc_id})")
                    return doc_id

                cur.execute(
                    "SELECT id, file_hash, extracted_text IS NOT DISTINCT FROM %s "
                    "FROM documents WHERE filename = %s",
                    (doc.extracted_text, doc.filename),
                )
                existing = cur.fetchone()
                if existing is None:
                    raise ValueError(f"Failed to get ID for existing document: {doc.filename}")
                existing_id, stored_hash, same_text = existing
                same = doc.file_hash == stored_hash if doc.file_hash and stored_hash else same_text
                if not same:
                    raise DuplicateDocumentError(
                        f"A different document is already stored as {doc.filename!r} "
                        f"(id {existing_id})"
                    )
                logger.warning(f"Document already exists: {doc.filename}")
                return int(existing_id)
        except Exception as e:
            logger.error(f"Failed to insert document: {error_summary(e)}")
            raise

    def get_by_id(self, doc_id: int) -> Document | None:
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
            with self._cursor() as cur:
                cur.execute(query, (doc_id,))
                row = cur.fetchone()
                if row:
                    return Document.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve document {doc_id}: {e}")
            raise

    def get_by_filename(self, filename: str) -> Document | None:
        """Retrieve document by filename."""
        query = """
            SELECT id, filename, file_hash, file_data, extracted_text,
                   metadata, uploaded_at, updated_at
            FROM documents
            WHERE filename = %s
        """

        try:
            with self._cursor() as cur:
                cur.execute(query, (filename,))
                row = cur.fetchone()
                if row:
                    return Document.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve document by filename: {error_summary(e)}")
            raise

    def get_id_by_filename(self, filename: str) -> int | None:
        """Get document ID by filename."""
        query = "SELECT id FROM documents WHERE filename = %s"
        try:
            with self._cursor() as cur:
                cur.execute(query, (filename,))
                result = cur.fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to get document ID: {error_summary(e)}")
            raise

    def search_by_metadata(self, filters: dict[str, Any]) -> list[Document]:
        """
        Search documents by metadata fields.

        Args:
            filters: Dict of metadata field filters (e.g., {'contract_type': 'NDA'}).
                Values are compared as text; no filters returns every document.

        Returns:
            List of matching Document objects
        """
        if not filters:
            return self.get_all()

        conditions = []
        params = []

        for key, value in filters.items():
            conditions.append("metadata->>%s = %s")
            # ->> yields text: 3 is '3', True is 'true'
            params.extend([key, value if isinstance(value, str) else json.dumps(value)])

        where_clause = " AND ".join(conditions)
        query = f"""
            SELECT id, filename, file_hash, file_data, extracted_text,
                   metadata, uploaded_at, updated_at
            FROM documents
            WHERE {where_clause}
        """

        try:
            with self._cursor() as cur:
                cur.execute(query, tuple(params))
                rows = cur.fetchall()
                return [Document.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to search documents: {error_summary(e)}")
            raise

    def get_all(self, limit: int | None = None) -> list[Document]:
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

        try:
            with self._cursor() as cur:
                if limit is not None:
                    cur.execute(query + " LIMIT %s", (limit,))
                else:
                    cur.execute(query)
                rows = cur.fetchall()
                return [Document.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve all documents: {error_summary(e)}")
            raise

    def update_extracted_text(self, doc_id: int, extracted_text: str) -> None:
        """Update extracted text for a document.  Raises DocumentNotFoundError if it is missing."""
        query = """
            UPDATE documents
            SET extracted_text = %s, updated_at = NOW()
            WHERE id = %s
        """

        try:
            with self._cursor() as cur:
                cur.execute(query, (extracted_text, doc_id))
                if cur.rowcount == 0:
                    raise DocumentNotFoundError(f"No document with id {doc_id}")
                logger.info(f"Updated extracted text for document {doc_id}")
        except Exception as e:
            logger.error(f"Failed to update extracted text: {error_summary(e)}")
            raise

    def update_metadata(self, doc_id: int, metadata: dict[str, Any]) -> None:
        """
        Merge *metadata* into a document's stored metadata.

        Top-level keys given here replace the stored ones; other stored keys
        are kept, so two writers do not erase each other's keys.

        Raises:
            DocumentNotFoundError: If the document does not exist
        """
        query = """
            UPDATE documents
            SET metadata = COALESCE(metadata, '{}'::jsonb) || %s, updated_at = NOW()
            WHERE id = %s
        """

        try:
            with self._cursor() as cur:
                cur.execute(query, (psycopg2.extras.Json(metadata), doc_id))
                if cur.rowcount == 0:
                    raise DocumentNotFoundError(f"No document with id {doc_id}")
                logger.info(f"Updated metadata for document {doc_id}")
        except Exception as e:
            logger.error(f"Failed to update metadata: {error_summary(e)}")
            raise

    def delete(self, doc_id: int) -> bool:
        """Delete a document (cascades to clauses).  Returns False if there was none."""
        query = "DELETE FROM documents WHERE id = %s"

        try:
            with self._cursor() as cur:
                cur.execute(query, (doc_id,))
                deleted: bool = cur.rowcount > 0
                if deleted:
                    logger.info(f"Deleted document {doc_id}")
                else:
                    logger.warning(f"Document {doc_id} not found; nothing deleted")
                return deleted
        except Exception as e:
            logger.error(f"Failed to delete document: {error_summary(e)}")
            raise

    def count(self) -> int:
        """Count total documents."""
        query = "SELECT COUNT(*) FROM documents"
        try:
            with self._cursor() as cur:
                cur.execute(query)
                result = cur.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Failed to count documents: {error_summary(e)}")
            raise


class ClauseRepository(_Repository):
    """Repository for Clause database operations."""

    @contextmanager
    def _embedding_cursor(self, vector: bool = True) -> Iterator[Any]:
        """Cursor for queries on clauses.embedding; a missing column gets a clear error."""
        try:
            with self._cursor(vector=vector) as cur:
                yield cur
        except psycopg2.errors.UndefinedColumn as e:
            raise ContractExError(_NO_EMBEDDING_COLUMN) from e

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
            with self._cursor() as cur:
                cur.execute(
                    query,
                    (
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
                        psycopg2.extras.Json(clause.metadata),
                    ),
                )
                result = cur.fetchone()
                clause_id = result[0] if result else 0
                logger.debug(f"Inserted clause {clause_id} for document {clause.document_id}")
                return clause_id
        except Exception as e:
            logger.error(f"Failed to insert clause: {error_summary(e)}")
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
                c.document_id,
                c.clause_text,
                c.clause_type,
                c.page_number,
                c.bbox_x,
                c.bbox_y,
                c.bbox_width,
                c.bbox_height,
                c.confidence_score,
                c.parent_clause_id,
                psycopg2.extras.Json(c.metadata),
            )
            for c in clauses
        ]

        try:
            with self._cursor() as cur:
                ids = execute_values(cur, query, values, fetch=True)
                clause_ids = [row[0] for row in ids]
                logger.info(f"Inserted {len(clause_ids)} clauses")
                return clause_ids
        except Exception as e:
            logger.error(f"Failed to batch insert clauses: {error_summary(e)}")
            raise

    def get_by_id(self, clause_id: int) -> Clause | None:
        """Retrieve clause by ID."""
        query = """
            SELECT id, document_id, clause_text, clause_type, page_number,
                   bbox_x, bbox_y, bbox_width, bbox_height,
                   confidence_score, parent_clause_id, metadata, created_at
            FROM clauses
            WHERE id = %s
        """

        try:
            with self._cursor() as cur:
                cur.execute(query, (clause_id,))
                row = cur.fetchone()
                if row:
                    return Clause.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve clause: {error_summary(e)}")
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
            with self._cursor() as cur:
                cur.execute(query, (document_id,))
                rows = cur.fetchall()
                return [Clause.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve clauses for document: {error_summary(e)}")
            raise

    def search_by_type(self, clause_type: str, limit: int | None = None) -> list[Clause]:
        """Search clauses by type across all documents."""
        query = """
            SELECT id, document_id, clause_text, clause_type, page_number,
                   bbox_x, bbox_y, bbox_width, bbox_height,
                   confidence_score, parent_clause_id, metadata, created_at
            FROM clauses
            WHERE clause_type = %s
            ORDER BY created_at DESC
        """

        try:
            with self._cursor() as cur:
                if limit is not None:
                    cur.execute(query + " LIMIT %s", (clause_type, limit))
                else:
                    cur.execute(query, (clause_type,))
                rows = cur.fetchall()
                return [Clause.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to search clauses by type: {error_summary(e)}")
            raise

    def delete_by_document(self, document_id: int) -> None:
        """Delete all clauses for a document."""
        query = "DELETE FROM clauses WHERE document_id = %s"

        try:
            with self._cursor() as cur:
                cur.execute(query, (document_id,))
                logger.info(f"Deleted clauses for document {document_id}")
        except Exception as e:
            logger.error(f"Failed to delete clauses: {error_summary(e)}")
            raise

    def count_by_document(self, document_id: int) -> int:
        """Count clauses for a document."""
        query = "SELECT COUNT(*) FROM clauses WHERE document_id = %s"
        try:
            with self._cursor() as cur:
                cur.execute(query, (document_id,))
                result = cur.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logger.error(f"Failed to count clauses: {error_summary(e)}")
            raise

    def update_embedding(self, clause_id: int, embedding: list[float]) -> None:
        """Store a vector embedding for a single clause."""
        with self._embedding_cursor() as cur:
            cur.execute(
                "UPDATE clauses SET embedding = %s WHERE id = %s",
                (embedding, clause_id),
            )

    def update_embeddings_batch(self, pairs: list[tuple[int, list[float]]]) -> None:
        """Bulk-update embeddings. pairs = [(clause_id, embedding), ...]"""
        with self._embedding_cursor() as cur:
            cur.executemany(
                "UPDATE clauses SET embedding = %s WHERE id = %s",
                [(emb, cid) for cid, emb in pairs],
            )

    def get_unembedded(self, document_id: int | None = None) -> list[Clause]:
        """Return clauses that have not yet been embedded."""
        base = """
            SELECT id, document_id, clause_text, clause_type, page_number,
                   bbox_x, bbox_y, bbox_width, bbox_height,
                   confidence_score, parent_clause_id, metadata, created_at
            FROM clauses
            WHERE embedding IS NULL
        """
        try:
            with self._embedding_cursor(vector=False) as cur:
                if document_id is not None:
                    cur.execute(base + " AND document_id = %s ORDER BY id", (document_id,))
                else:
                    cur.execute(base + " ORDER BY id")
                return [Clause.from_db_row(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"Failed to retrieve unembedded clauses: {error_summary(e)}")
            raise


class ProcessingLogRepository(_Repository):
    """Repository for ProcessingLog database operations."""

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
            with self._cursor() as cur:
                cur.execute(
                    query, (log.document_id, log.processing_stage, log.status, log.error_message)
                )
                result = cur.fetchone()
                log_id = result[0] if result else 0
                logger.debug(f"Inserted processing log {log_id}")
                return log_id
        except Exception as e:
            logger.error(f"Failed to insert processing log: {error_summary(e)}")
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
            with self._cursor() as cur:
                cur.execute(query, (document_id,))
                rows = cur.fetchall()
                return [ProcessingLog.from_db_row(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve processing logs: {error_summary(e)}")
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
            with self._cursor() as cur:
                cur.execute(query)
                rows = cur.fetchall()
                return [row[0] for row in rows]
        except Exception as e:
            logger.error(f"Failed to retrieve failed documents: {error_summary(e)}")
            raise

    def get_latest_by_stage(self, document_id: int, stage: str) -> ProcessingLog | None:
        """Get most recent log entry for a document and stage."""
        query = """
            SELECT id, document_id, processing_stage, status, error_message, created_at
            FROM processing_log
            WHERE document_id = %s AND processing_stage = %s
            ORDER BY created_at DESC
            LIMIT 1
        """

        try:
            with self._cursor() as cur:
                cur.execute(query, (document_id, stage))
                row = cur.fetchone()
                if row:
                    return ProcessingLog.from_db_row(row)
                return None
        except Exception as e:
            logger.error(f"Failed to retrieve latest log: {error_summary(e)}")
            raise
