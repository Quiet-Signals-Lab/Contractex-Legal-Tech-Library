"""Utility functions for export, comparison, normalization, routing, and auditing."""

from contractex.utils.audit import (
    AuditBackend,
    AuditEvent,
    AuditEventType,
    AuditLogger,
    JSONLAuditBackend,
    NullAuditBackend,
    PostgresAuditBackend,
)
from contractex.utils.provenance import ChunkRecord, ProvenanceTracker
from contractex.utils.routing import (
    ConfidenceRouter,
    ReviewItem,
    RoutingDecision,
    RoutingResult,
)

__all__ = [
    # Provenance tracking
    "ProvenanceTracker",
    "ChunkRecord",
    # Confidence routing
    "ConfidenceRouter",
    "RoutingDecision",
    "ReviewItem",
    "RoutingResult",
    # Audit logging
    "AuditLogger",
    "AuditEvent",
    "AuditEventType",
    "AuditBackend",
    "NullAuditBackend",
    "JSONLAuditBackend",
    "PostgresAuditBackend",
]
