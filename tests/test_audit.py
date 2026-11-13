"""
Unit tests for AuditLogger, AuditEvent, and the JSONL backend.

No database, no network — only in-memory and temp-file operations.
"""

from __future__ import annotations

import json
import threading

import pytest

from contractex.utils.audit import (
    AuditEvent,
    AuditEventType,
    AuditLogger,
    JSONLAuditBackend,
    NullAuditBackend,
)

# ---------------------------------------------------------------------------
# AuditEvent
# ---------------------------------------------------------------------------


class TestAuditEvent:
    def test_auto_uuid(self):
        e1 = AuditEvent(event_type=AuditEventType.DOCUMENT_INGESTED)
        e2 = AuditEvent(event_type=AuditEventType.DOCUMENT_INGESTED)
        assert e1.event_id != e2.event_id

    def test_timestamp_utc(self):
        event = AuditEvent(event_type=AuditEventType.DOCUMENT_INGESTED)
        assert event.timestamp.tzinfo is not None
        assert event.timestamp.utcoffset().total_seconds() == 0

    def test_to_jsonl_line_ends_with_newline(self):
        event = AuditEvent(event_type=AuditEventType.DOCUMENT_INGESTED)
        line = event.to_jsonl_line()
        assert line.endswith("\n")

    def test_to_jsonl_line_is_valid_json(self):
        event = AuditEvent(
            event_type=AuditEventType.FIELDS_EXTRACTED,
            document_id="doc-123",
            fields_extracted=["name", "dob"],
        )
        line = event.to_jsonl_line()
        data = json.loads(line)
        assert data["event_type"] == "fields_extracted"
        assert data["document_id"] == "doc-123"

    def test_overall_confidence_bounds(self):
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            AuditEvent(
                event_type=AuditEventType.FIELDS_EXTRACTED,
                overall_confidence=1.5,  # out of range
            )


# ---------------------------------------------------------------------------
# NullAuditBackend
# ---------------------------------------------------------------------------


class TestNullAuditBackend:
    def test_write_is_noop(self):
        backend = NullAuditBackend()
        event = AuditEvent(event_type=AuditEventType.DOCUMENT_INGESTED)
        backend.write(event)  # Should not raise

    def test_close_is_noop(self):
        backend = NullAuditBackend()
        backend.close()  # Should not raise

    def test_context_manager(self):
        with NullAuditBackend() as backend:
            backend.write(AuditEvent(event_type=AuditEventType.DOCUMENT_INGESTED))


# ---------------------------------------------------------------------------
# JSONLAuditBackend
# ---------------------------------------------------------------------------


class TestJSONLAuditBackend:
    def test_writes_jsonl_file(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        backend = JSONLAuditBackend(path)
        event = AuditEvent(
            event_type=AuditEventType.DOCUMENT_INGESTED,
            document_id="doc-001",
        )
        backend.write(event)
        backend.close()

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["document_id"] == "doc-001"

    def test_appends_multiple_events(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        backend = JSONLAuditBackend(path)
        for i in range(5):
            backend.write(
                AuditEvent(
                    event_type=AuditEventType.FIELDS_EXTRACTED,
                    document_id=f"doc-{i}",
                )
            )
        backend.close()

        lines = path.read_text().strip().split("\n")
        assert len(lines) == 5

    def test_read_all(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        backend = JSONLAuditBackend(path)
        backend.write(AuditEvent(event_type=AuditEventType.DOCUMENT_INGESTED, document_id="d1"))
        backend.write(AuditEvent(event_type=AuditEventType.FIELDS_EXTRACTED, document_id="d2"))
        backend.close()

        events = JSONLAuditBackend.read_all(path)
        assert len(events) == 2
        assert events[0].event_type == AuditEventType.DOCUMENT_INGESTED
        assert events[1].document_id == "d2"

    def test_creates_parent_directories(self, tmp_path):
        path = tmp_path / "nested" / "dir" / "audit.jsonl"
        backend = JSONLAuditBackend(path)
        backend.write(AuditEvent(event_type=AuditEventType.DOCUMENT_INGESTED))
        backend.close()
        assert path.exists()

    def test_thread_safe_concurrent_writes(self, tmp_path):
        path = tmp_path / "concurrent.jsonl"
        backend = JSONLAuditBackend(path)
        n_threads = 10
        n_events_per_thread = 20

        def write_events():
            for _ in range(n_events_per_thread):
                backend.write(AuditEvent(event_type=AuditEventType.DOCUMENT_INGESTED))

        threads = [threading.Thread(target=write_events) for _ in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        backend.close()

        lines = [line for line in path.read_text().split("\n") if line.strip()]
        assert len(lines) == n_threads * n_events_per_thread
        # Every line must be valid JSON
        for line in lines:
            json.loads(line)

    def test_context_manager(self, tmp_path):
        path = tmp_path / "ctx.jsonl"
        with JSONLAuditBackend(path) as backend:
            backend.write(AuditEvent(event_type=AuditEventType.PIPELINE_ERROR))
        events = JSONLAuditBackend.read_all(path)
        assert len(events) == 1


# ---------------------------------------------------------------------------
# AuditLogger facade
# ---------------------------------------------------------------------------


class TestAuditLogger:
    def test_null_factory(self):
        logger = AuditLogger.null()
        # Should not raise
        logger.log_ingestion("doc-1")
        logger.close()

    def test_from_jsonl_factory(self, tmp_path):
        path = tmp_path / "audit.jsonl"
        with AuditLogger.from_jsonl(path) as audit:
            audit.log_ingestion("doc-1", source_url="https://docs.test")
        events = JSONLAuditBackend.read_all(path)
        assert len(events) == 1
        assert events[0].source_url == "https://docs.test"

    def test_log_ingestion(self, tmp_path):
        path = tmp_path / "a.jsonl"
        with AuditLogger.from_jsonl(path) as audit:
            audit.log_ingestion(
                "doc-42",
                source_url="https://ecfr.gov/",
                session_id="session-1",
                user_id="worker-1",
            )
        events = JSONLAuditBackend.read_all(path)
        assert events[0].event_type == AuditEventType.DOCUMENT_INGESTED
        assert events[0].document_id == "doc-42"
        assert events[0].session_id == "session-1"

    def test_log_extraction(self, tmp_path):
        path = tmp_path / "a.jsonl"
        with AuditLogger.from_jsonl(path) as audit:
            audit.log_extraction(
                "doc-42",
                fields_extracted=["surname", "given_name"],
                fields_rejected=["mrz_line2"],
                overall_confidence=0.91,
            )
        events = JSONLAuditBackend.read_all(path)
        assert events[0].event_type == AuditEventType.FIELDS_EXTRACTED
        assert events[0].fields_extracted == ["surname", "given_name"]
        assert events[0].fields_rejected == ["mrz_line2"]
        assert events[0].overall_confidence == pytest.approx(0.91)

    def test_log_review_request(self, tmp_path):
        path = tmp_path / "a.jsonl"
        with AuditLogger.from_jsonl(path) as audit:
            audit.log_review_request("doc-42", fields=["dob", "passport_number"])
        events = JSONLAuditBackend.read_all(path)
        assert events[0].event_type == AuditEventType.REVIEW_REQUESTED
        assert "dob" in events[0].fields_extracted

    def test_log_deletion(self, tmp_path):
        path = tmp_path / "a.jsonl"
        with AuditLogger.from_jsonl(path) as audit:
            audit.log_deletion("doc-42", user_id="gdpr-eraser")
        events = JSONLAuditBackend.read_all(path)
        assert events[0].event_type == AuditEventType.DOCUMENT_DELETED
        assert events[0].user_id == "gdpr-eraser"

    def test_log_error(self, tmp_path):
        path = tmp_path / "a.jsonl"
        with AuditLogger.from_jsonl(path) as audit:
            audit.log_error("doc-42", error_message="OCR engine timed out")
        events = JSONLAuditBackend.read_all(path)
        assert events[0].event_type == AuditEventType.PIPELINE_ERROR
        assert "OCR" in events[0].error_message

    def test_backend_error_does_not_propagate(self):
        """AuditLogger must never interrupt calling code on write failure."""
        from unittest.mock import MagicMock

        bad_backend = MagicMock()
        bad_backend.write.side_effect = RuntimeError("disk full")
        audit = AuditLogger(backend=bad_backend)
        # Should log via standard logging, not raise
        audit.log_ingestion("doc-1")

    def test_extra_metadata_passed_through(self, tmp_path):
        path = tmp_path / "a.jsonl"
        with AuditLogger.from_jsonl(path) as audit:
            audit.log_ingestion("doc-42", pipeline_version="1.2.3")
        events = JSONLAuditBackend.read_all(path)
        assert events[0].metadata.get("pipeline_version") == "1.2.3"

    def test_invalid_event_field_does_not_propagate(self, tmp_path):
        """A bad value (confidence given as a percentage) must not break the pipeline."""
        path = tmp_path / "a.jsonl"
        with AuditLogger.from_jsonl(path) as audit:
            audit.log_extraction("doc-1", ["party"], overall_confidence=92)
            audit.log_ingestion("doc-2")
        assert [e.document_id for e in JSONLAuditBackend.read_all(path)] == ["doc-2"]


# ---------------------------------------------------------------------------
# PostgresAuditBackend
# ---------------------------------------------------------------------------


def test_storage_sql_does_not_create_the_audit_backend_table():
    """schema v2 had its own, different ``audit_log``; every audit insert then failed."""
    import re
    from pathlib import Path

    import contractex.storage
    from contractex.utils.audit import PostgresAuditBackend

    def created_tables(sql: str) -> set[str]:
        return set(re.findall(r"CREATE TABLE (?:IF NOT EXISTS )?(\w+)", sql))

    (audit_table,) = created_tables(PostgresAuditBackend._DDL)
    storage_dir = Path(contractex.storage.__file__).parent
    for sql_file in sorted(storage_dir.rglob("*.sql")):
        assert audit_table not in created_tables(sql_file.read_text()), sql_file.name


@pytest.mark.integration
class TestPostgresAuditBackend:
    @pytest.fixture
    def dsn(self, test_database):
        import psycopg2

        dsn = psycopg2.extensions.make_dsn(
            dbname=test_database["db_name"],
            user=test_database["user"],
            password=test_database["password"],
            host=test_database["host"],
            port=test_database["port"],
        )
        yield dsn
        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        conn.cursor().execute("DROP TABLE IF EXISTS audit_log")
        conn.close()

    @staticmethod
    def _query(dsn, sql):
        import psycopg2

        conn = psycopg2.connect(dsn)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall() if cur.description else []
        conn.close()
        return rows

    def test_events_are_written(self, dsn):
        with AuditLogger.from_postgres(dsn) as audit:
            audit.log_ingestion("doc-1", source_url="https://docs.test/a.pdf")
            audit.log_deletion("doc-1", user_id="dpo")
        rows = self._query(dsn, "SELECT event_type FROM audit_log ORDER BY timestamp")
        assert rows == [("document_ingested",), ("document_deleted",)]

    def test_reconnects_after_a_dropped_connection(self, dsn):
        audit = AuditLogger.from_postgres(dsn)
        audit.log_ingestion("doc-1")
        self._query(
            dsn,
            "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            "WHERE datname = current_database() AND pid <> pg_backend_pid()",
        )
        audit.log_ingestion("doc-2")
        audit.log_ingestion("doc-3")
        audit.close()
        rows = self._query(dsn, "SELECT document_id FROM audit_log ORDER BY document_id")
        assert rows == [("doc-1",), ("doc-2",), ("doc-3",)]

    def test_incompatible_existing_table_is_an_error_at_setup(self, dsn):
        """A table of the same name with other columns must not swallow every event."""
        from contractex.exceptions import ContractExError
        from contractex.utils.audit import PostgresAuditBackend

        self._query(dsn, "CREATE TABLE audit_log (id BIGSERIAL PRIMARY KEY, doc_id TEXT)")
        with pytest.raises(ContractExError, match="audit_log"):
            PostgresAuditBackend(dsn)
