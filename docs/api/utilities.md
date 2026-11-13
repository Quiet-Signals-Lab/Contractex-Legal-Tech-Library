# Review routing and audit

Triage of extracted fields by confidence, and an audit trail of what was
processed.  Neither is called by the built-in pipelines; wire them in where you need them.

::: contractex.utils.ConfidenceRouter

::: contractex.utils.RoutingResult

::: contractex.utils.RoutingDecision

::: contractex.utils.ReviewItem

::: contractex.utils.AuditLogger

::: contractex.utils.AuditEvent

::: contractex.utils.AuditEventType

::: contractex.utils.AuditBackend

::: contractex.utils.NullAuditBackend

::: contractex.utils.JSONLAuditBackend

::: contractex.utils.PostgresAuditBackend
