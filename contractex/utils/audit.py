"""
Compliance-grade audit logging for legal document pipelines.

Records every material operation — document ingested, fields extracted, human
review requested, errors — to an append-only, structured log.  This is the
component that satisfies GDPR Article 30 record-of-processing requirements and
makes the pipeline auditable for SOC 2 / ISO 27001 evidence.

Backends are pluggable:
  * ``JSONLAuditBackend``    — newline-delimited JSON file (zero dependency)
  * ``PostgresAuditBackend`` — PostgreSQL table (requires contractex[storage])
  * ``NullAuditBackend``     — no-op sink for testing

The ``AuditLogger`` facade wraps any backend and provides convenience methods
for the most common event types.  All writes are thread-safe.  Backend errors
are captured and re-emitted via the standard ``logging`` module so they never
propagate to calling code.

Usage::

    # File-backed (typical for a single-machine pipeline)
    with AuditLogger.from_jsonl("audit/pipeline.jsonl") as audit:
        audit.log_ingestion(document_id="doc-123",
                            source_url="https://ecfr.gov/...",
                            user_id="pipeline-worker-1")
        # ... run extraction ...
        audit.log_extraction(
            document_id="doc-123",
            fields_extracted=["surname", "given_name", "dob"],
            fields_rejected=["mrz_line2"],
            overall_confidence=0.92,
        )

    # Postgres-backed (multi-worker deployments)
    audit = AuditLogger.from_postgres(dsn="postgresql://user:pw@host/db")
"""

from __future__ import annotations

import logging
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Event taxonomy
# ---------------------------------------------------------------------------


class AuditEventType(str, Enum):
    """Taxonomy of auditable pipeline events."""

    DOCUMENT_INGESTED = "document_ingested"
    DOCUMENT_LOADED = "document_loaded"
    FIELDS_EXTRACTED = "fields_extracted"
    FIELD_REJECTED = "field_rejected"      # confidence below auto-reject threshold
    REVIEW_REQUESTED = "review_requested"  # routed to human-review queue
    REVIEW_COMPLETED = "review_completed"
    DOCUMENT_DELETED = "document_deleted"
    ACCESS_DENIED = "access_denied"
    PIPELINE_ERROR = "pipeline_error"


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------


class AuditEvent(BaseModel):
    """A single auditable event.  All fields are serialisable to JSON."""

    event_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique event identifier (UUID v4)",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp when the event occurred",
    )
    event_type: AuditEventType = Field(..., description="Type of event")

    # Actor / session context
    document_id: str | None = Field(None, description="Stable document identifier")
    session_id: str | None = Field(None, description="Processing session / job ID")
    user_id: str | None = Field(
        None,
        description="User or service account that triggered the event",
    )
    source_url: str | None = Field(None, description="Source URL of the document")

    # Extraction specifics
    fields_extracted: list[str] = Field(
        default_factory=list,
        description="Names of fields successfully extracted",
    )
    fields_rejected: list[str] = Field(
        default_factory=list,
        description="Names of fields rejected (below confidence threshold)",
    )
    overall_confidence: float | None = Field(
        None,
        ge=0.0,
        le=1.0,
        description="Aggregate confidence score for the extraction",
    )

    # Error details
    error_message: str | None = Field(None, description="Error message if applicable")

    # Flexible metadata — must remain JSON-serialisable
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional structured metadata (pipeline-defined)",
    )

    def to_jsonl_line(self) -> str:
        """Serialise to a single JSON line (no trailing newline in model_dump_json)."""
        return self.model_dump_json() + "\n"


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------


class AuditBackend(ABC):
    """Abstract backend for persisting AuditEvents."""

    @abstractmethod
    def write(self, event: AuditEvent) -> None:
        """Persist *event*."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release resources held by this backend."""
        ...

    def __enter__(self) -> AuditBackend:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


class NullAuditBackend(AuditBackend):
    """No-op sink — for tests or when auditing is explicitly disabled."""

    def write(self, event: AuditEvent) -> None:
        pass

    def close(self) -> None:
        pass


class JSONLAuditBackend(AuditBackend):
    """
    Append-only JSONL (newline-delimited JSON) file backend.

    Each event occupies exactly one line, making the log trivially ingestible
    by log aggregators (Splunk, Loki, BigQuery, jq, etc.).

    Thread-safe via an internal ``threading.Lock``.

    Args:
        path: Path to the audit log file.  Parent directories are created
              automatically.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._file = self.path.open("a", encoding="utf-8")

    def write(self, event: AuditEvent) -> None:
        line = event.to_jsonl_line()
        with self._lock:
            self._file.write(line)
            self._file.flush()

    def close(self) -> None:
        with self._lock:
            if not self._file.closed:
                self._file.close()

    @classmethod
    def read_all(cls, path: str | Path) -> list[AuditEvent]:
        """Read and deserialise all events from a JSONL file (for inspection / tests)."""
        events: list[AuditEvent] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(AuditEvent.model_validate_json(line))
        return events


class PostgresAuditBackend(AuditBackend):
    """
    PostgreSQL audit backend.

    Requires the ``storage`` extra::

        pip install contractex[storage]

    The table is created automatically on first use (``ensure_table=True``).
    Each write uses ``autocommit`` mode to guarantee durability without
    wrapping the caller's transaction.

    DDL::

        CREATE TABLE IF NOT EXISTS audit_log (
            event_id           UUID PRIMARY KEY,
            timestamp          TIMESTAMPTZ NOT NULL,
            event_type         TEXT NOT NULL,
            document_id        TEXT,
            session_id         TEXT,
            user_id            TEXT,
            source_url         TEXT,
            fields_extracted   TEXT[],
            fields_rejected    TEXT[],
            overall_confidence NUMERIC(4,3),
            error_message      TEXT,
            metadata           JSONB
        );
    """

    _DDL = """
        CREATE TABLE IF NOT EXISTS audit_log (
            event_id           UUID PRIMARY KEY,
            timestamp          TIMESTAMPTZ NOT NULL,
            event_type         TEXT NOT NULL,
            document_id        TEXT,
            session_id         TEXT,
            user_id            TEXT,
            source_url         TEXT,
            fields_extracted   TEXT[],
            fields_rejected    TEXT[],
            overall_confidence NUMERIC(4,3),
            error_message      TEXT,
            metadata           JSONB
        );
    """

    _INSERT = """
        INSERT INTO audit_log (
            event_id, timestamp, event_type, document_id, session_id,
            user_id, source_url, fields_extracted, fields_rejected,
            overall_confidence, error_message, metadata
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (event_id) DO NOTHING;
    """

    def __init__(self, dsn: str, ensure_table: bool = True) -> None:
        try:
            import psycopg2
            import psycopg2.extras
        except ImportError as exc:
            raise ImportError(
                "psycopg2-binary is required for PostgresAuditBackend. "
                "Install with: pip install contractex[storage]"
            ) from exc

        self._psycopg2 = psycopg2
        self._conn = psycopg2.connect(dsn)
        self._conn.autocommit = True
        self._lock = threading.Lock()

        if ensure_table:
            with self._conn.cursor() as cur:
                cur.execute(self._DDL)

    def write(self, event: AuditEvent) -> None:
        import psycopg2.extras  # type: ignore[import]

        with self._lock, self._conn.cursor() as cur:
            cur.execute(
                self._INSERT,
                (
                    event.event_id,
                    event.timestamp,
                    event.event_type.value,
                    event.document_id,
                    event.session_id,
                    event.user_id,
                    event.source_url,
                    event.fields_extracted or None,
                    event.fields_rejected or None,
                    event.overall_confidence,
                    event.error_message,
                    psycopg2.extras.Json(event.metadata),
                ),
            )

    def close(self) -> None:
        with self._lock:
            self._conn.close()


# ---------------------------------------------------------------------------
# AuditLogger facade
# ---------------------------------------------------------------------------


class AuditLogger:
    """
    Thread-safe facade that records AuditEvents via a pluggable backend.

    Backend failures are caught and re-emitted via the standard ``logging``
    module so they never interrupt the calling pipeline.

    Factories
    ---------
    * ``AuditLogger.from_jsonl(path)``   — JSONL file backend
    * ``AuditLogger.from_postgres(dsn)`` — PostgreSQL backend
    * ``AuditLogger.null()``             — no-op backend (testing)

    Example::

        with AuditLogger.from_jsonl("audit/pipeline.jsonl") as al:
            al.log_ingestion("doc-1", source_url="https://example.com/doc.pdf")
            al.log_extraction("doc-1", ["name", "dob"], overall_confidence=0.91)
    """

    def __init__(self, backend: AuditBackend | None = None) -> None:
        self._backend: AuditBackend = backend or NullAuditBackend()

    # ------------------------------------------------------------------
    # Factories
    # ------------------------------------------------------------------

    @classmethod
    def from_jsonl(cls, path: str | Path) -> AuditLogger:
        """Create an AuditLogger backed by a JSONL file."""
        return cls(backend=JSONLAuditBackend(path))

    @classmethod
    def from_postgres(cls, dsn: str) -> AuditLogger:
        """Create an AuditLogger backed by PostgreSQL."""
        return cls(backend=PostgresAuditBackend(dsn))

    @classmethod
    def null(cls) -> AuditLogger:
        """Create a no-op logger (useful in tests)."""
        return cls(backend=NullAuditBackend())

    # ------------------------------------------------------------------
    # Core write
    # ------------------------------------------------------------------

    def log(self, event: AuditEvent) -> None:
        """Write a pre-built AuditEvent.  Failures are logged, not raised."""
        try:
            self._backend.write(event)
        except Exception as exc:
            logger.error("AuditLogger write failed: %s", exc)

    # ------------------------------------------------------------------
    # Convenience helpers
    # ------------------------------------------------------------------

    def log_ingestion(
        self,
        document_id: str,
        source_url: str | None = None,
        session_id: str | None = None,
        user_id: str | None = None,
        **metadata: Any,
    ) -> None:
        """Record that a document was ingested into the pipeline."""
        self.log(
            AuditEvent(
                event_type=AuditEventType.DOCUMENT_INGESTED,
                document_id=document_id,
                source_url=source_url,
                session_id=session_id,
                user_id=user_id,
                metadata=metadata,
            )
        )

    def log_extraction(
        self,
        document_id: str,
        fields_extracted: list[str],
        fields_rejected: list[str] | None = None,
        overall_confidence: float | None = None,
        session_id: str | None = None,
        **metadata: Any,
    ) -> None:
        """Record the outcome of a field-extraction step."""
        self.log(
            AuditEvent(
                event_type=AuditEventType.FIELDS_EXTRACTED,
                document_id=document_id,
                fields_extracted=fields_extracted,
                fields_rejected=fields_rejected or [],
                overall_confidence=overall_confidence,
                session_id=session_id,
                metadata=metadata,
            )
        )

    def log_review_request(
        self,
        document_id: str,
        fields: list[str],
        session_id: str | None = None,
        **metadata: Any,
    ) -> None:
        """Record that fields were routed to the human-review queue."""
        self.log(
            AuditEvent(
                event_type=AuditEventType.REVIEW_REQUESTED,
                document_id=document_id,
                fields_extracted=fields,
                session_id=session_id,
                metadata=metadata,
            )
        )

    def log_review_completion(
        self,
        document_id: str,
        session_id: str | None = None,
        **metadata: Any,
    ) -> None:
        """Record that human review was completed for a document."""
        self.log(
            AuditEvent(
                event_type=AuditEventType.REVIEW_COMPLETED,
                document_id=document_id,
                session_id=session_id,
                metadata=metadata,
            )
        )

    def log_deletion(
        self,
        document_id: str,
        user_id: str | None = None,
        session_id: str | None = None,
        **metadata: Any,
    ) -> None:
        """Record a GDPR-right-to-erasure deletion event."""
        self.log(
            AuditEvent(
                event_type=AuditEventType.DOCUMENT_DELETED,
                document_id=document_id,
                user_id=user_id,
                session_id=session_id,
                metadata=metadata,
            )
        )

    def log_error(
        self,
        document_id: str | None,
        error_message: str,
        session_id: str | None = None,
        **metadata: Any,
    ) -> None:
        """Record a pipeline error."""
        self.log(
            AuditEvent(
                event_type=AuditEventType.PIPELINE_ERROR,
                document_id=document_id,
                error_message=error_message,
                session_id=session_id,
                metadata=metadata,
            )
        )

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def close(self) -> None:
        """Close the underlying backend."""
        self._backend.close()

    def __enter__(self) -> AuditLogger:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()
