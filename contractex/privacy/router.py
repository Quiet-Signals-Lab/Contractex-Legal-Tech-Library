"""
PrivacyAwareLLMRouter — enforces privacy controls before every LLM API call.

This component sits **between** the task pipeline and the LLM provider.  The
built-in tasks, ``TaskPipeline`` and ``LegalRAGPipeline`` reach providers only
through it (via ``guard()``).

Routing flow
------------
1. Resolve the document's ``PrivacyProfile``.  A dict (e.g. a ``LegalDoc``
   reloaded from JSON) is validated into a profile; anything else that is not
   ``None`` raises ``TypeError``.  Documents with no profile get the router's
   ``default_profile``.
2. If routing is ``"blocked"`` → raise ``PrivacyBlockedError`` before any
   prompt reaches the provider.
3. If routing is ``"local_only"`` → the provider must be a ``LocalProvider``
   instance; otherwise raise ``PrivacyRoutingError``.  The router does not
   check where a ``LocalProvider``'s Ollama host runs.
4. If ``sensitivity`` is ``"confidential"`` or ``"restricted"`` (and the caller
   has not marked the text as already redacted) → detect and redact PII in
   *this* prompt.  Every call is redacted independently.
5. Call the provider with the clean prompt.
6. Optionally restore placeholders in the response (strings at any depth).

When a prompt contains several documents, pass them all to ``guard()``: the
strictest sensitivity and routing among them apply.

Usage
-----
::

    from contractex.privacy import PrivacyAwareLLMRouter, PrivacyProfile
    from contractex.llm.local_provider import LocalProvider

    router = PrivacyAwareLLMRouter()
    doc.privacy_profile = PrivacyProfile(sensitivity="restricted")

    result = router.route(doc, prompt, MySchema, LocalProvider(model="llama3.1:8b"))

    # Or wrap a provider so every call on it is enforced for this document
    llm = router.guard(LocalProvider(model="llama3.1:8b"), doc)
    summary = llm.complete(prompt)
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Iterator
from typing import Any, Literal, cast

from pydantic import BaseModel

from contractex.exceptions import ContractExError
from contractex.llm.base import LLMProvider
from contractex.llm.local_provider import LocalProvider
from contractex.privacy.detector import PIIDetector
from contractex.privacy.profile import PrivacyProfile
from contractex.privacy.redactor import PIIRedactor, RedactionMap

logger = logging.getLogger(__name__)

# Ascending restriction
_SENSITIVITY_ORDER = ["public", "confidential", "restricted", "secret"]
_ROUTING_ORDER = ["any", "local_only", "blocked"]


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

    Typically: a provider that is not a ``LocalProvider`` is used for a
    document that requires ``llm_routing="local_only"``.
    """


# ---------------------------------------------------------------------------
# Profile helpers
# ---------------------------------------------------------------------------


def resolve_profile(doc: Any, default: PrivacyProfile) -> PrivacyProfile:
    """Return *doc*'s privacy profile, failing closed on anything unrecognised."""
    profile = getattr(doc, "privacy_profile", None)
    if profile is None:
        return default
    if isinstance(profile, PrivacyProfile):
        return profile
    if isinstance(profile, dict):
        return PrivacyProfile.model_validate(profile)
    raise TypeError(
        f"privacy_profile must be a PrivacyProfile or dict, got {type(profile).__name__}"
    )


def strictest(profiles: list[PrivacyProfile]) -> PrivacyProfile:
    """Combine profiles, keeping the most restrictive sensitivity and routing."""
    if len(profiles) == 1:
        return profiles[0]
    routing = max((p.llm_routing or "any" for p in profiles), key=_ROUTING_ORDER.index)
    return PrivacyProfile(
        sensitivity=max((p.sensitivity for p in profiles), key=_SENSITIVITY_ORDER.index),
        llm_routing=cast(Literal["any", "local_only", "blocked"], routing),
    )


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
        When ``True`` (default), detect and redact PII in every prompt for
        documents whose profile ``requires_redaction``.
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

        Raises
        ------
        PrivacyBlockedError
            If the document's routing is ``"blocked"``.
        PrivacyRoutingError
            If the provider is not permitted for this document.
        """
        result = self._route(
            self._profile_for([doc]),
            _language(doc),
            prompt,
            provider,
            lambda p: provider.extract_structured(p, schema),
            restore_redaction,
        )
        return cast(BaseModel, result)

    def route_completion(
        self,
        doc: Any,
        prompt: str,
        provider: LLMProvider,
        *,
        restore_redaction: bool = False,
        **kwargs: Any,
    ) -> str:
        """Enforce privacy controls then call ``provider.complete``."""
        result = self._route(
            self._profile_for([doc]),
            _language(doc),
            prompt,
            provider,
            lambda p: provider.complete(p, **kwargs),
            restore_redaction,
        )
        return cast(str, result)

    def guard(self, provider: LLMProvider, *docs: Any) -> LLMProvider:
        """
        Wrap *provider* so every call on it is enforced for *docs*.

        Raises ``PrivacyBlockedError`` / ``PrivacyRoutingError`` immediately if
        the provider may never be used for these documents.  Responses are
        restored (placeholders replaced by the original values) except when
        streaming, where a placeholder can be split across tokens.
        """
        profile = self._profile_for(list(docs))
        self._enforce_routing(profile, provider)
        return PrivacyGuardedProvider(self, provider, profile, _language(docs[0]) if docs else "en")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _profile_for(self, docs: list[Any]) -> PrivacyProfile:
        return strictest(
            [resolve_profile(d, self._default_profile) for d in docs] or [self._default_profile]
        )

    def _route(
        self,
        profile: PrivacyProfile,
        language: str,
        prompt: str,
        provider: LLMProvider,
        call: Any,
        restore: bool,
    ) -> Any:
        clean_prompt, redaction_map = self._prepare(profile, language, prompt, provider)
        result = call(clean_prompt)
        if restore and redaction_map is not None:
            result = self._restore(result, redaction_map)
        return result

    def _prepare(
        self, profile: PrivacyProfile, language: str, prompt: str, provider: LLMProvider
    ) -> tuple[str, RedactionMap | None]:
        """Enforce routing, then redact *prompt* if the profile requires it."""
        self._enforce_routing(profile, provider)
        if not self._auto_redact or not profile.requires_redaction:
            return prompt, None

        spans = self._detector.detect(prompt, language=language)
        if not spans:
            return prompt, None

        redacted = self._redactor.redact(prompt, spans)
        entity_types = list(redacted.entity_types_redacted)
        profile.contains_pii = True
        profile.pii_entities_found = list(dict.fromkeys(profile.pii_entities_found + entity_types))

        logger.info(
            "Redacted %d PII span(s) (%s) before LLM call",
            redacted.span_count,
            ", ".join(entity_types),
        )
        return redacted.text, redacted.redaction_map

    @staticmethod
    def _enforce_routing(profile: PrivacyProfile, provider: LLMProvider) -> None:
        """Raise if provider is not permitted by this profile."""
        if profile.is_blocked:
            raise PrivacyBlockedError(
                f"LLM processing is blocked for this document "
                f"(sensitivity={profile.sensitivity!r}, "
                f"llm_routing={profile.llm_routing!r})."
            )

        if profile.is_local_only and not isinstance(provider, LocalProvider):
            raise PrivacyRoutingError(
                f"Document requires local-only routing but provider is "
                f"'{type(provider).__name__}'.  Use contractex.llm.LocalProvider (Ollama)."
            )

    def _restore(self, result: Any, redaction_map: RedactionMap) -> Any:
        """Replace placeholders in a string or in every string of a model."""

        def walk(value: Any) -> Any:
            if isinstance(value, str):
                return self._redactor.restore(value, redaction_map)
            if isinstance(value, list):
                return [walk(v) for v in value]
            if isinstance(value, dict):
                return {k: walk(v) for k, v in value.items()}
            return value

        if isinstance(result, BaseModel):
            return type(result).model_validate(walk(result.model_dump()))
        return walk(result)


@functools.cache
def default_router() -> PrivacyAwareLLMRouter:
    """The router used by built-in tasks that are not given one explicitly."""
    return PrivacyAwareLLMRouter()


def _language(doc: Any) -> str:
    return getattr(doc, "language", "en") or "en"


class PrivacyGuardedProvider(LLMProvider):
    """
    An ``LLMProvider`` whose every call is routed through a
    ``PrivacyAwareLLMRouter`` for a fixed privacy profile.  Created by
    ``PrivacyAwareLLMRouter.guard()``.
    """

    def __init__(
        self,
        router: PrivacyAwareLLMRouter,
        provider: LLMProvider,
        profile: PrivacyProfile,
        language: str,
    ) -> None:
        self._router = router
        self.wrapped = provider
        self._profile = profile
        self._language = language

    def extract_structured(
        self,
        prompt: str,
        schema: type[BaseModel],
        temperature: float = 0.0,
        max_tokens: int | None = None,
    ) -> BaseModel:
        return cast(
            BaseModel,
            self._router._route(
                self._profile,
                self._language,
                prompt,
                self.wrapped,
                lambda p: self.wrapped.extract_structured(
                    p, schema, temperature=temperature, max_tokens=max_tokens
                ),
                True,
            ),
        )

    def complete(
        self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs: Any
    ) -> str:
        return cast(
            str,
            self._router._route(
                self._profile,
                self._language,
                prompt,
                self.wrapped,
                lambda p: self.wrapped.complete(
                    p, temperature=temperature, max_tokens=max_tokens, **kwargs
                ),
                True,
            ),
        )

    def stream_complete(  # type: ignore[override]
        self, prompt: str, temperature: float = 0.7, max_tokens: int | None = None, **kwargs: Any
    ) -> Iterator[str]:
        clean, _ = self._router._prepare(self._profile, self._language, prompt, self.wrapped)
        return self.wrapped.stream_complete(
            clean, temperature=temperature, max_tokens=max_tokens, **kwargs
        )

    def estimate_cost(self, text: str) -> float:
        return self.wrapped.estimate_cost(text)

    def count_tokens(self, text: str) -> int:
        return self.wrapped.count_tokens(text)

    @property
    def context_window(self) -> int:
        return self.wrapped.context_window

    @property
    def model(self) -> str:
        return self.wrapped.model

    def supports_structured_output(self) -> bool:
        return self.wrapped.supports_structured_output()
