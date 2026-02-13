"""
Domain models for legal document analysis.

These dataclasses represent business entities and encapsulate domain logic,
providing type-safe interfaces between database and application code.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class Document:
    """Represents a source legal document (PDF, DOCX, etc.)."""

    # Core fields
    id: Optional[int] = None
    filename: str = ""
    file_hash: Optional[str] = None

    # Content
    file_data: Optional[bytes] = None
    extracted_text: Optional[str] = None

    # Metadata (flexible JSONB storage)
    # Expected keys: contract_type, parties, effective_date, expiration_date,
    # governing_law, amendment_to, custom_tags
    metadata: dict[str, Any] = field(default_factory=dict)

    # Timestamps
    uploaded_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: tuple) -> "Document":
        """
        Convert psycopg2 query result tuple to Document object.

        Assumes row order matches schema:
        (id, filename, file_hash, file_data, extracted_text, metadata, uploaded_at, updated_at)
        """
        return cls(
            id=row[0],
            filename=row[1],
            file_hash=row[2],
            file_data=row[3],
            extracted_text=row[4],
            metadata=row[5] if row[5] else {},
            uploaded_at=row[6],
            updated_at=row[7],
        )

    @staticmethod
    def compute_hash(file_data: bytes) -> str:
        """Compute SHA-256 hash for deduplication."""
        return hashlib.sha256(file_data).hexdigest()

    def update_metadata(self, **kwargs) -> None:
        """Update metadata fields while preserving existing values."""
        self.metadata.update(kwargs)

    def get_metadata_field(self, key: str, default=None):
        """Safely retrieve metadata field with default."""
        return self.metadata.get(key, default)


@dataclass
class Clause:
    """Represents an extracted clause from a document."""

    # Core fields
    id: Optional[int] = None
    document_id: int = 0

    # Content
    clause_text: str = ""
    clause_type: Optional[str] = None  # termination, payment, liability, etc.

    # Spatial metadata for visual grounding
    page_number: Optional[int] = None
    bbox_x: Optional[float] = None
    bbox_y: Optional[float] = None
    bbox_width: Optional[float] = None
    bbox_height: Optional[float] = None

    # Extraction metadata
    confidence_score: Optional[float] = None
    parent_clause_id: Optional[int] = None

    # Flexible metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Vector embedding (populated by the retrieval pipeline, not returned by from_db_row)
    embedding: Optional[list[float]] = None

    # Timestamp
    created_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: tuple) -> "Clause":
        """
        Convert psycopg2 query result tuple to Clause object.

        Assumes row order matches schema:
        (id, document_id, clause_text, clause_type, page_number,
         bbox_x, bbox_y, bbox_width, bbox_height, confidence_score,
         parent_clause_id, metadata, created_at)
        """
        return cls(
            id=row[0],
            document_id=row[1],
            clause_text=row[2],
            clause_type=row[3],
            page_number=row[4],
            bbox_x=row[5],
            bbox_y=row[6],
            bbox_width=row[7],
            bbox_height=row[8],
            confidence_score=row[9],
            parent_clause_id=row[10],
            metadata=row[11] if row[11] else {},
            created_at=row[12],
        )

    def has_bounding_box(self) -> bool:
        """Check if clause has complete bounding box information."""
        return all(
            [
                self.bbox_x is not None,
                self.bbox_y is not None,
                self.bbox_width is not None,
                self.bbox_height is not None,
            ]
        )

    def get_bounding_box(self) -> Optional[dict[str, float]]:
        """Return bounding box as dict, or None if incomplete."""
        if (
            self.has_bounding_box()
            and self.bbox_x is not None
            and self.bbox_y is not None
            and self.bbox_width is not None
            and self.bbox_height is not None
        ):
            return {
                "x": self.bbox_x,
                "y": self.bbox_y,
                "width": self.bbox_width,
                "height": self.bbox_height,
            }
        return None


@dataclass
class ProcessingLog:
    """Audit trail entry for document processing lifecycle."""

    id: Optional[int] = None
    document_id: Optional[int] = None

    # Processing state
    processing_stage: str = ""  # uploaded, extracted, embedded, indexed
    status: str = ""  # pending, completed, failed

    # Error tracking
    error_message: Optional[str] = None

    # Timestamp
    created_at: Optional[datetime] = None

    @classmethod
    def from_db_row(cls, row: tuple) -> "ProcessingLog":
        """
        Convert psycopg2 query result tuple to ProcessingLog object.

        Assumes row order matches schema:
        (id, document_id, processing_stage, status, error_message, created_at)
        """
        return cls(
            id=row[0],
            document_id=row[1],
            processing_stage=row[2],
            status=row[3],
            error_message=row[4],
            created_at=row[5],
        )

    def is_failed(self) -> bool:
        """Check if this log entry represents a failure."""
        return self.status == "failed"

    def is_completed(self) -> bool:
        """Check if this log entry represents successful completion."""
        return self.status == "completed"


# Constants for standardization
class ClauseType:
    """Controlled vocabulary for clause types."""

    TERMINATION = "termination"
    PAYMENT = "payment"
    LIABILITY = "liability"
    INDEMNIFICATION = "indemnification"
    CONFIDENTIALITY = "confidentiality"
    GOVERNING_LAW = "governing_law"
    DISPUTE_RESOLUTION = "dispute_resolution"
    INTELLECTUAL_PROPERTY = "intellectual_property"
    WARRANTY = "warranty"
    FORCE_MAJEURE = "force_majeure"
    ASSIGNMENT = "assignment"
    AMENDMENT = "amendment"
    OTHER = "other"


class ProcessingStage:
    """Controlled vocabulary for processing stages."""

    UPLOADED = "uploaded"
    EXTRACTED = "extracted"
    EMBEDDED = "embedded"
    INDEXED = "indexed"


class ProcessingStatus:
    """Controlled vocabulary for processing status."""

    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
