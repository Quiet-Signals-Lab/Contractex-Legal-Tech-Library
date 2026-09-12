"""
PIIRedactor — replaces detected PII spans with typed placeholders (or hashes,
masks, or encrypted values) before text reaches an LLM.

Key properties
--------------
* **Consistent replacement** — the same literal value in a document always
  receives the same placeholder (``GARCIA`` on line 3 and line 47 both become
  ``<PERSON_1>``).
* **Reversible** — ``restore()`` puts original values back: REPLACE via the
  ``RedactionMap`` (which therefore holds the original PII in plaintext and is
  as sensitive as the source document), ENCRYPT by decrypting each token with
  the key.  MASK and HASH are one-way.
* **Strategy per entity type** — the default strategy may be overridden
  per entity type (e.g. REPLACE for names, HASH for IBANs).

Redaction strategies
--------------------
* ``REPLACE`` — substitute with ``<ENTITY_TYPE_N>`` placeholder (default).
* ``HASH``    — HMAC-SHA256 of the original value, hex-encoded, prefixed with
                the entity type: ``<PERSON_HASH:3a4f...>``.
* ``MASK``    — ``***`` (for display; not reversible).
* ``ENCRYPT`` — AES-256-GCM encryption.  Requires ``cryptography`` package
                (``pip install contractex[privacy]``).  Caller must supply
                a 32-byte key via ``PIIRedactor(encryption_key=...)``.

Usage
-----
::

    from contractex.privacy.detector import PIIDetector
    from contractex.privacy.redactor import PIIRedactor

    detector = PIIDetector()
    redactor = PIIRedactor()

    spans = detector.detect(text)
    result = redactor.redact(text, spans)

    # Send result.text to LLM …

    # Later: restore from result.redaction_map (if strategy is REPLACE)
    original = redactor.restore(llm_output, result.redaction_map)
"""

from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass, field
from typing import Any

from contractex.privacy.detector import PIISpan, merge_overlapping
from contractex.privacy.profile import RedactionStrategy

_ENC_TOKEN = re.compile(r"<[A-Z0-9_]+_ENC:([0-9a-f]+)>")

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class RedactionMap:
    """
    Forward and reverse mapping produced by a single ``redact()`` call.

    Attributes
    ----------
    placeholder_to_original:
        Maps REPLACE placeholders (e.g. ``"<PERSON_1>"``) to original values.
        This is plaintext PII.  ENCRYPT tokens are never stored here.
    original_to_placeholder:
        Reverse index used to give repeated values the same placeholder.
        Held in memory only; ``serialise()`` does not write it.
    counters:
        Per-entity-type incrementing counter used to generate unique labels.
    encryption_key:
        Only present when strategy is ENCRYPT.  Stored as bytes; callers
        are responsible for securing this.
    """

    placeholder_to_original: dict[str, str] = field(default_factory=dict)
    original_to_placeholder: dict[str, str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    encryption_key: bytes | None = None

    def register(self, entity_type: str, original: str, placeholder: str) -> None:
        """Record a mapping in both directions."""
        self.placeholder_to_original[placeholder] = original
        self.original_to_placeholder[original] = placeholder

    def next_label(self, entity_type: str) -> str:
        """Return the next placeholder label for *entity_type*."""
        n = self.counters.get(entity_type, 0) + 1
        self.counters[entity_type] = n
        return f"<{entity_type}_{n}>"

    def serialise(self) -> dict[str, Any]:
        """
        Serialise to a JSON-compatible dict.

        The result contains the original REPLACE values in plaintext: store it
        with the same protection as the source document, never in an audit log.
        """
        return {
            "placeholder_to_original": self.placeholder_to_original,
            "counters": self.counters,
            # encryption_key is intentionally excluded from serialisation
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RedactionMap:
        forward = data.get("placeholder_to_original", {})
        reverse = {v: k for k, v in forward.items()}
        return cls(
            placeholder_to_original=forward,
            original_to_placeholder=reverse,
            counters=data.get("counters", {}),
        )


@dataclass
class RedactedText:
    """
    The output of a single ``PIIRedactor.redact()`` call.

    Attributes
    ----------
    text:
        Redacted text safe to pass to an LLM.
    redaction_map:
        Mapping required to restore original values (REPLACE and ENCRYPT
        strategies only).
    entity_types_redacted:
        Set of entity type strings that were redacted.
    span_count:
        Total number of PII spans that were replaced.
    """

    text: str
    redaction_map: RedactionMap
    entity_types_redacted: set[str] = field(default_factory=set)
    span_count: int = 0


# ---------------------------------------------------------------------------
# Main redactor class
# ---------------------------------------------------------------------------


class PIIRedactor:
    """
    Replaces PII spans in text with safe placeholders.

    Parameters
    ----------
    default_strategy:
        Default replacement strategy.  Defaults to ``REPLACE``.
    strategy_overrides:
        Per-entity-type strategy overrides, e.g.
        ``{"IBAN_CODE": RedactionStrategy.HASH}``.
    encryption_key:
        32-byte key for AES-256-GCM (required when any entity uses
        ``ENCRYPT`` strategy).  Generates a random key if not supplied
        and ENCRYPT is requested.
    hmac_key:
        Secret key for HMAC-SHA256 hashing (HASH strategy).  Generates
        a random key if not supplied.
    """

    def __init__(
        self,
        default_strategy: RedactionStrategy = RedactionStrategy.REPLACE,
        strategy_overrides: dict[str, RedactionStrategy] | None = None,
        encryption_key: bytes | None = None,
        hmac_key: bytes | None = None,
    ) -> None:
        self._default_strategy = default_strategy
        self._strategy_overrides = strategy_overrides or {}
        self._encryption_key = encryption_key
        self._hmac_key = hmac_key or os.urandom(32)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def redact(self, text: str, spans: list[PIISpan]) -> RedactedText:
        """
        Replace all *spans* in *text* according to the configured strategies.

        Spans may arrive in any order and may overlap; overlapping spans are
        merged so every covered character is redacted.  Placeholder labels
        that already occur in *text* are skipped, so ``restore()`` is exact.

        Parameters
        ----------
        text:
            Original text containing PII.
        spans:
            Sorted (ascending start) list of PII spans from ``PIIDetector``.

        Returns
        -------
        RedactedText
            Contains the redacted text and the mapping needed for restoration.
        """
        rmap = RedactionMap(encryption_key=self._encryption_key)
        entity_types: set[str] = set()
        spans = merge_overlapping(spans, text)

        # Process in reverse so offsets stay valid
        result = text
        for span in reversed(spans):
            original = text[span.start : span.end]
            strategy = self._strategy_overrides.get(span.entity_type, self._default_strategy)
            placeholder = self._make_placeholder(span, original, strategy, rmap, text)
            result = result[: span.start] + placeholder + result[span.end :]
            entity_types.add(span.entity_type)

        return RedactedText(
            text=result,
            redaction_map=rmap,
            entity_types_redacted=entity_types,
            span_count=len(spans),
        )

    def restore(self, text: str, redaction_map: RedactionMap) -> str:
        """
        Restore placeholders in *text* back to their original values.

        Only works for ``REPLACE`` and ``ENCRYPT`` strategies.  ``MASK``
        and ``HASH`` replacements are irreversible.  ENCRYPT tokens are
        decrypted with ``redaction_map.encryption_key`` (or this redactor's
        key); without a key they are left in place.

        Parameters
        ----------
        text:
            Text containing placeholders (e.g. LLM output).
        redaction_map:
            The ``RedactionMap`` produced by the matching ``redact()`` call.

        Returns
        -------
        str
            Text with placeholders replaced by original values (where
            mapping exists).
        """
        result = text
        for placeholder, original in redaction_map.placeholder_to_original.items():
            result = result.replace(placeholder, original)
        key = redaction_map.encryption_key or self._encryption_key
        if key:
            result = _ENC_TOKEN.sub(lambda m: self._decrypt_or_keep(m, key), result)
        return result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _make_placeholder(
        self,
        span: PIISpan,
        original: str,
        strategy: RedactionStrategy,
        rmap: RedactionMap,
        text: str,
    ) -> str:
        # Consistent replacement: reuse existing placeholder for same value
        if original in rmap.original_to_placeholder:
            return rmap.original_to_placeholder[original]

        if strategy == RedactionStrategy.ENCRYPT:
            placeholder = self._encrypt(span, original, rmap)
            rmap.original_to_placeholder[original] = placeholder
            return placeholder

        if strategy == RedactionStrategy.MASK:
            return "***"

        if strategy == RedactionStrategy.HASH:
            digest = hmac.new(self._hmac_key, original.encode(), hashlib.sha256).hexdigest()
            placeholder = f"<{span.entity_type}_HASH:{digest[:16]}>"
            # HASH is not reversible — don't register in forward map
            return placeholder

        # REPLACE.  Skip labels already present in the source text, otherwise
        # restore() would also rewrite that pre-existing text.
        placeholder = rmap.next_label(span.entity_type)
        while placeholder in text:
            placeholder = rmap.next_label(span.entity_type)
        rmap.register(span.entity_type, original, placeholder)
        return placeholder

    def _encrypt(self, span: PIISpan, original: str, rmap: RedactionMap) -> str:
        """
        AES-256-GCM encrypt *original*.

        Requires ``cryptography`` (``pip install contractex[privacy]``); raises
        ``ImportError`` rather than silently using a different strategy.
        """
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError as exc:
            raise ImportError(
                "RedactionStrategy.ENCRYPT requires the cryptography package: "
                "pip install 'contractex[privacy]'"
            ) from exc

        key = self._ensure_encryption_key(rmap)
        nonce = os.urandom(12)
        ct = AESGCM(key).encrypt(nonce, original.encode(), None)
        return f"<{span.entity_type}_ENC:{(nonce + ct).hex()}>"

    def _ensure_encryption_key(self, rmap: RedactionMap) -> bytes:
        if self._encryption_key:
            return self._encryption_key
        key = os.urandom(32)
        self._encryption_key = key
        rmap.encryption_key = key
        return key

    def _decrypt_or_keep(self, match: re.Match[str], key: bytes) -> str:
        """Decrypt one token; leave it untouched if it was altered (e.g. by an LLM)."""
        try:
            return self._decrypt_token(match.group(1), key)
        except Exception:
            return match.group(0)

    def _decrypt_token(self, token_hex: str, key: bytes) -> str:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        data = bytes.fromhex(token_hex)
        nonce, ct = data[:12], data[12:]
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode()
