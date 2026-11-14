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

The ``llm_routing`` field is normally derived from ``sensitivity``.  Callers
may set it explicitly to make routing stricter (for example ``"local_only"`` on
a ``public`` document), never looser: the routing enforced is always the
stricter of the two (``effective_routing``).

A profile holds only what the router enforces or reports.  How PII is
replaced is configured on ``PIIRedactor``; retention periods and consent
records belong to your own records, where something acts on them.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

Routing = Literal["any", "local_only", "blocked"]

# Ascending restriction
ROUTING_ORDER: tuple[Routing, ...] = ("any", "local_only", "blocked")
_ROUTING_FOR_SENSITIVITY: dict[str, Routing] = {
    "public": "any",
    "confidential": "any",
    "restricted": "local_only",
    "secret": "blocked",
}


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
    llm_routing:
        Stricter routing than ``sensitivity`` implies.  If ``None``, routing
        is derived from ``sensitivity``.  A looser value is ignored.
    """

    sensitivity: Literal["public", "confidential", "restricted", "secret"] = "public"
    contains_pii: bool = False
    pii_entities_found: list[str] = Field(default_factory=list)
    redaction_applied: bool = False

    # Optional stricter routing; if None, derived from sensitivity
    llm_routing: Routing | None = None

    @model_validator(mode="after")
    def _derive_routing(self) -> PrivacyProfile:
        """
        Store the routing that will be enforced, so ``llm_routing`` reads as:

        * public        → any
        * confidential  → any  (but auto-redaction will be applied)
        * restricted    → local_only
        * secret        → blocked

        or the explicit value when that is stricter.
        """
        self.llm_routing = self.effective_routing
        return self

    @property
    def effective_routing(self) -> Routing:
        """
        The routing enforced: the stricter of ``sensitivity``'s own routing and
        ``llm_routing``.

        Computed on every read, so raising ``sensitivity`` after construction
        (by assignment, ``model_copy(update=...)`` or an edited dict) tightens
        routing at once.  A value this model does not recognise blocks.
        """
        derived = _ROUTING_FOR_SENSITIVITY.get(self.sensitivity, "blocked")
        explicit: Routing = "any" if self.llm_routing is None else self.llm_routing
        if explicit not in ROUTING_ORDER:
            return "blocked"
        return max(derived, explicit, key=ROUTING_ORDER.index)

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
        return self.effective_routing == "blocked"

    @property
    def is_local_only(self) -> bool:
        """True when only local (Ollama) providers are permitted."""
        return self.effective_routing == "local_only"
