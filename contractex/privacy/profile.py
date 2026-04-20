"""
PrivacyProfile — per-document privacy controls attached to every LegalDoc.

The profile travels with the document through every pipeline stage and is
read by ``PrivacyAwareLLMRouter`` before any LLM API call is made.

Sensitivity levels (ascending restriction)
-------------------------------------------
* ``"public"``       — no restrictions; any provider may be used.
* ``"confidential"`` — redaction applied before sending to cloud LLMs.
* ``"restricted"``   — local-only routing; cloud LLMs blocked.
* ``"secret"``       — all LLM processing blocked; returns error.

LLM routing values
------------------
* ``"any"``          — use any configured provider.
* ``"local_only"``   — route to ``LocalProvider`` (Ollama) only.
* ``"blocked"``      — do not send to any LLM; raise ``PrivacyBlockedError``.

The ``llm_routing`` field is normally derived from ``sensitivity``, but
callers may override it explicitly for edge cases.

GDPR fields
-----------
* ``retention_days``      — ``None`` means no expiry; set to fulfil Art. 5(1)(e).
* ``data_subject_ids``    — IDs of natural persons for Art. 17 erasure requests.
* ``consent_reference``   — links to a consent record for Art. 7 compliance.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class RedactionStrategy(str, Enum):
    """How PII should be replaced in text before LLM consumption."""

    REPLACE = "replace"
    """Substitute with typed placeholder e.g. ``<PERSON_1>``."""

    HASH = "hash"
    """Replace with keyed HMAC-SHA256 hash (one-way, suitable for analytics)."""

    MASK = "mask"
    """Replace with ``***`` (for display / logging — not reversible)."""

    ENCRYPT = "encrypt"
    """AES-256-GCM encryption with caller-supplied key (reversible)."""


class PrivacyProfile(BaseModel):
    """
    Privacy controls attached to a ``LegalDoc``.

    Attributes
    ----------
    sensitivity:
        Broad sensitivity classification.  Controls default routing and
        whether auto-redaction is applied.
    contains_pii:
        Set by ``PIIDetector``, not the caller.
    pii_entities_found:
        Entity type strings detected by ``PIIDetector`` (e.g. ``["PERSON",
        "PASSPORT_NUMBER"]``).
    redaction_applied:
        ``True`` once ``PIIRedactor.redact()`` has been applied to the text
        that will reach an LLM.
    redaction_strategy:
        How PII is replaced.  Defaults to ``REPLACE`` (typed placeholders).
    llm_routing:
        Override for LLM provider selection.  If ``None``, routing is derived
        from ``sensitivity`` automatically.
    retention_days:
        GDPR Art. 5(1)(e) — ``None`` means no expiry.
    data_subject_ids:
        Natural-person IDs for GDPR Art. 17 right-to-erasure requests.
    consent_reference:
        Identifier linking to a consent record for GDPR Art. 7 compliance.
    """

    sensitivity: Literal["public", "confidential", "restricted", "secret"] = "public"
    contains_pii: bool = False
    pii_entities_found: list[str] = Field(default_factory=list)
    redaction_applied: bool = False
    redaction_strategy: RedactionStrategy = RedactionStrategy.REPLACE

    # Optional explicit routing override; if None, derived from sensitivity
    llm_routing: Literal["any", "local_only", "blocked"] | None = None

    # GDPR fields
    retention_days: int | None = None
    data_subject_ids: list[str] = Field(default_factory=list)
    consent_reference: str | None = None

    @model_validator(mode="after")
    def _derive_routing(self) -> PrivacyProfile:
        """
        If ``llm_routing`` is not explicitly set, derive it from
        ``sensitivity``:

        * public        → any
        * confidential  → any  (but auto-redaction will be applied)
        * restricted    → local_only
        * secret        → blocked
        """
        if self.llm_routing is None:
            self.llm_routing = {
                "public": "any",
                "confidential": "any",
                "restricted": "local_only",
                "secret": "blocked",
            }[self.sensitivity]
        return self

    @property
    def requires_redaction(self) -> bool:
        """
        True when the document must be redacted before any LLM call.

        Redaction is required when sensitivity is at least ``"confidential"``
        and the document has not yet been redacted.
        """
        needs = self.sensitivity in ("confidential", "restricted")
        return needs and not self.redaction_applied

    @property
    def is_blocked(self) -> bool:
        """True when no LLM may process this document."""
        return self.llm_routing == "blocked"

    @property
    def is_local_only(self) -> bool:
        """True when only local (Ollama) providers are permitted."""
        return self.llm_routing == "local_only"
