"""
Privacy layer for ContractEx.

This module sits between the document loader and every LLM API call.
It provides PII detection, redaction, privacy profiling, and LLM routing
based on document sensitivity.

Usage
-----
Minimal — let the pipeline auto-detect and redact::

    from contractex.privacy import PIIDetector, PIIRedactor, PrivacyProfile

    detector = PIIDetector()
    redactor = PIIRedactor()

    spans = detector.detect(doc.full_text)
    if spans:
        redacted = redactor.redact(doc.full_text, spans)
        # redacted.text is safe to send to an external LLM

Full pipeline with router::

    from contractex.privacy import PrivacyAwareLLMRouter, PrivacyProfile

    profile = PrivacyProfile(sensitivity="confidential")
    router = PrivacyAwareLLMRouter(detector=detector, redactor=redactor)
    result = router.route(doc, prompt, MySchema, llm_provider)

Optional Presidio backend::

    pip install contractex[privacy]
    # presidio-analyzer and presidio-anonymizer are now available
"""

from __future__ import annotations

from contractex.privacy.detector import PIIDetector, PIISpan
from contractex.privacy.profile import PrivacyProfile, RedactionStrategy
from contractex.privacy.redactor import PIIRedactor, RedactedText, RedactionMap
from contractex.privacy.router import PrivacyAwareLLMRouter

__all__ = [
    "PIIDetector",
    "PIISpan",
    "PIIRedactor",
    "RedactedText",
    "RedactionMap",
    "PrivacyProfile",
    "RedactionStrategy",
    "PrivacyAwareLLMRouter",
]
