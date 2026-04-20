"""
PrivacyAwareLLMRouter — enforces privacy controls before every LLM API call.

This component sits **between** the task pipeline and the LLM provider.
It replaces direct ``LLMProvider`` calls in ``ContractExtractor`` and all
task pipelines.

Routing flow
------------
1. Read ``doc.privacy_profile.llm_routing``.
2. If ``"blocked"`` → raise ``PrivacyBlockedError`` immediately.
3. If ``"local_only"`` → assert the supplied provider is a
   ``LocalProvider``; raise ``PrivacyRoutingError`` otherwise.
4. If ``redaction_applied`` is ``False`` and ``sensitivity >= "confidential"``
   → auto-detect and auto-redact before calling provider.
5. Call ``provider.extract_structured(prompt, schema)`` or
   ``provider.complete(prompt)`` as appropriate.
6. Optionally de-anonymize the response if caller supplies decryption key.

Auto-detection & auto-redaction
--------------------------------
When ``privacy_profile.requires_redaction`` is ``True`` and the router is
constructed with ``auto_redact=True`` (default), the router will:

* Run ``PIIDetector`` on the text embedded in *prompt*.
* Replace PII with ``PIIRedactor``.
* Update ``doc.privacy_profile`` in-place (``redaction_applied=True``,
  ``pii_entities_found`` populated).
* Pass the clean prompt to the provider.

The original prompt is never logged or stored.

Usage
-----
::

    from contractex.privacy import PrivacyAwareLLMRouter, PrivacyProfile
    from contractex.llm.openai_provider import OpenAIProvider

    provider = OpenAIProvider(model="gpt-4o")
    router = PrivacyAwareLLMRouter()

    doc.privacy_profile = PrivacyProfile(sensitivity="confidential")
    result = router.route(doc, prompt, MySchema, provider)
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

from contractex.exceptions import ContractExError
from contractex.llm.base import LLMProvider
from contractex.privacy.detector import PIIDetector
from contractex.privacy.profile import PrivacyProfile
from contractex.privacy.redactor import PIIRedactor

logger = logging.getLogger(__name__)

# Sensitivity levels in ascending order
_SENSITIVITY_ORDER = ["public", "confidential", "restricted", "secret"]


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class PrivacyBlockedError(ContractExError):
    """
    Raised when a document's privacy profile forbids any LLM processing.

    ``sensitivity="secret"`` or ``llm_routing="blocked"`` triggers this.
    """


class PrivacyRoutingError(ContractExError):
    """
    Raised when the requested LLM provider is not permitted for this document.

    Typically: a cloud provider is used for a document that requires
    ``llm_routing="local_only"``.
    """


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class PrivacyAwareLLMRouter:
    """
    Routes LLM calls through privacy enforcement.

    Parameters
    ----------
    detector:
        ``PIIDetector`` instance.  A default instance is created if not
        supplied.
    redactor:
        ``PIIRedactor`` instance.  A default instance is created if not
        supplied.
    auto_redact:
        When ``True`` (default), auto-detect and auto-redact PII when
        ``privacy_profile.requires_redaction`` is ``True``.
    default_profile:
        Profile applied to documents that have no ``privacy_profile`` set.
        Defaults to ``PrivacyProfile(sensitivity="public")``.
    """

    def __init__(
        self,
        detector: PIIDetector | None = None,
        redactor: PIIRedactor | None = None,
        auto_redact: bool = True,
        default_profile: PrivacyProfile | None = None,
    ) -> None:
        self._detector = detector or PIIDetector()
        self._redactor = redactor or PIIRedactor()
        self._auto_redact = auto_redact
        self._default_profile = default_profile or PrivacyProfile(sensitivity="public")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def route(
        self,
        doc: Any,  # LegalDoc — using Any to avoid circular import
        prompt: str,
        schema: type[BaseModel],
        provider: LLMProvider,
        *,
        restore_redaction: bool = False,
    ) -> BaseModel:
        """
        Enforce privacy controls then call ``provider.extract_structured``.

        Parameters
        ----------
        doc:
            The ``LegalDoc`` being processed.  Its ``privacy_profile`` is
            read and potentially mutated (``redaction_applied``,
            ``pii_entities_found``).
        prompt:
            The full prompt that would be sent to the LLM.
        schema:
            Pydantic schema for structured extraction.
        provider:
            The LLM provider to call (after privacy checks pass).
        restore_redaction:
            If ``True`` and the strategy is ``REPLACE``, attempt to
            de-anonymize field values in the response.

        Returns
        -------
        BaseModel
            Instance of *schema* from the provider.

        Raises
        ------
        PrivacyBlockedError
            If the document's routing is ``"blocked"``.
        PrivacyRoutingError
            If the provider is not permitted for this document.
        """
        profile = self._resolve_profile(doc)
        self._enforce_routing(profile, provider)
        clean_prompt, redaction_map = self._maybe_redact(prompt, profile, doc)

        result = provider.extract_structured(clean_prompt, schema)

        if restore_redaction and redaction_map is not None:
            result = self._restore_in_model(result, redaction_map)

        return result

    def route_completion(
        self,
        doc: Any,
        prompt: str,
        provider: LLMProvider,
        *,
        restore_redaction: bool = False,
        **kwargs: Any,
    ) -> str:
        """
        Enforce privacy controls then call ``provider.complete``.

        Returns the completion string.
        """
        profile = self._resolve_profile(doc)
        self._enforce_routing(profile, provider)
        clean_prompt, redaction_map = self._maybe_redact(prompt, profile, doc)

        response = provider.complete(clean_prompt, **kwargs)

        if restore_redaction and redaction_map is not None:
            response = self._redactor.restore(response, redaction_map)

        return response

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_profile(self, doc: Any) -> PrivacyProfile:
        """Return the document's privacy profile, falling back to default."""
        profile = getattr(doc, "privacy_profile", None)
        return profile if isinstance(profile, PrivacyProfile) else self._default_profile

    def _enforce_routing(self, profile: PrivacyProfile, provider: LLMProvider) -> None:
        """Raise if provider is not permitted by this profile."""
        if profile.is_blocked:
            raise PrivacyBlockedError(
                f"LLM processing is blocked for this document "
                f"(sensitivity={profile.sensitivity!r}, "
                f"llm_routing={profile.llm_routing!r})."
            )

        if profile.is_local_only:
            provider_class = type(provider).__name__
            # Check by class name to avoid importing LocalProvider here
            if "Local" not in provider_class:
                raise PrivacyRoutingError(
                    f"Document requires local-only routing but provider is "
                    f"'{provider_class}'.  Use contractex.llm.LocalProvider (Ollama)."
                )

    def _maybe_redact(
        self,
        prompt: str,
        profile: PrivacyProfile,
        doc: Any,
    ) -> tuple[str, Any | None]:
        """
        If auto-redact is enabled and required, redact *prompt*.

        Returns the (possibly redacted) prompt and the RedactionMap (or None).
        """
        if not self._auto_redact or not profile.requires_redaction:
            return prompt, None

        language = getattr(doc, "language", "en") or "en"
        spans = self._detector.detect(prompt, language=language)

        if not spans:
            return prompt, None

        redacted = self._redactor.redact(prompt, spans)
        entity_types = list(redacted.entity_types_redacted)

        # Mutate the profile in-place
        profile.contains_pii = True
        profile.redaction_applied = True
        profile.pii_entities_found = list(
            dict.fromkeys(profile.pii_entities_found + entity_types)
        )

        logger.info(
            "Auto-redacted %d PII span(s) (%s) before LLM call",
            redacted.span_count,
            ", ".join(entity_types),
        )
        return redacted.text, redacted.redaction_map

    @staticmethod
    def _restore_in_model(model: BaseModel, redaction_map: Any) -> BaseModel:
        """
        Attempt to replace placeholders in all string fields of *model*.

        Returns a new model instance with placeholders replaced.
        """
        from contractex.privacy.redactor import PIIRedactor, RedactionMap

        if not isinstance(redaction_map, RedactionMap):
            return model

        redactor = PIIRedactor()
        updates: dict[str, Any] = {}
        for field_name, value in model.model_dump().items():
            if isinstance(value, str):
                restored = redactor.restore(value, redaction_map)
                if restored != value:
                    updates[field_name] = restored
        if updates:
            return model.model_copy(update=updates)
        return model
