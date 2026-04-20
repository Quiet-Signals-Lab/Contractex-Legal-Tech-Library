"""
Database layer for legal document analysis.

This module provides a clean abstraction over PostgreSQL storage with:
- Domain models (Document, Clause, ProcessingLog)
- Repository pattern for database operations
- Connection management with context managers
- Idempotent setup and initialization

Usage:
    from contractex.storage import DocumentRepository, Document
    from contractex.storage.connection import get_connection

    # Create a document
    doc = Document(
        filename="contract.pdf",
        extracted_text="...",
        metadata={"contract_type": "NDA"}
    )

    # Store in database
    repo = DocumentRepository()
    doc_id = repo.insert(doc)

    # Retrieve
    retrieved = repo.get_by_id(doc_id)
"""

from __future__ import annotations

# Models
# Configuration
from contractex.storage.config import get_db_config

# Connection utilities
from contractex.storage.connection import (
    DatabaseConnection,
    get_connection,
    get_cursor,
    test_connection,
)
from contractex.storage.models import (
    Clause,
    ClauseType,
    Document,
    ProcessingLog,
    ProcessingStage,
    ProcessingStatus,
)

# Repositories
from contractex.storage.repository import (
    ClauseRepository,
    DocumentRepository,
    ProcessingLogRepository,
)

__all__ = [
    # Models
    "Document",
    "Clause",
    "ProcessingLog",
    "ClauseType",
    "ProcessingStage",
    "ProcessingStatus",
    # Repositories
    "DocumentRepository",
    "ClauseRepository",
    "ProcessingLogRepository",
    # Connection
    "DatabaseConnection",
    "get_connection",
    "get_cursor",
    "test_connection",
    # Config
    "get_db_config",
]
