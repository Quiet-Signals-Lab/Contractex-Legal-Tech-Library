"""
PIIDetector — detects personally identifiable information in text.

Default backend: Microsoft Presidio (``pip install contractex[privacy]``).
Automatic fallback: regex-based detection when Presidio is not installed.

The regex fallback is intentionally conservative — it catches the most
common PII patterns without dependencies, so the privacy layer always
functions even in minimal installs.

Supported entity types (default detection set)
-----------------------------------------------
* PERSON, EMAIL_ADDRESS, PHONE_NUMBER, LOCATION
* PASSPORT_NUMBER, NATIONAL_ID, DRIVERS_LICENSE
* CREDIT_CARD, IBAN_CODE, US_SSN
* DATE_OF_BIRTH
* MEDICAL_LICENSE (configurable)
* ORGANIZATION (configurable — may be intentional in legal docs)

Language support
----------------
Presidio: en, es, fr, de, it, pt, nl (depends on spacy models installed).
Regex fallback: en only.

Custom recognizers
------------------
Use ``add_recognizer()`` to inject domain-specific patterns (e.g. Moldovan
personal identification numbers, CUII codes, etc.)::

    from contractex.privacy.detector import PIIDetector, RegexPIIRecognizer

    detector = PIIDetector()
    detector.add_recognizer(RegexPIIRecognizer(
        entity_type="MDA_IDNP",
        pattern=r"\\b\\d{13}\\b",
        context_words=["IDNP", "identificare"],
        languages=["ro"],
    ))
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass
class PIISpan:
    """
    A detected PII occurrence in text.

    Attributes
    ----------
    entity_type: str
        Entity type label (e.g. ``"PERSON"``, ``"EMAIL_ADDRESS"``).
    start: int
        Start character offset (inclusive).
    end: int
        End character offset (exclusive).
    score: float
        Detection confidence in [0, 1].
    text: str
        The matched text fragment.
    language: str
        Language code used for detection.
    """

    entity_type: str
    start: int
    end: int
    score: float
    text: str
    language: str = "en"


@dataclass
class RegexPIIRecognizer:
    """
    A custom regex-based recognizer for project-specific entity types.

    Parameters
    ----------
    entity_type:
        Label to attach to matches (e.g. ``"MDA_IDNP"``).
    pattern:
        Python ``re`` compatible regular expression.
    context_words:
        Surrounding words that increase confidence (used by Presidio's
        context-aware scoring; ignored by the regex fallback).
    languages:
        BCP-47 language codes this recognizer applies to.
    score:
        Base confidence assigned to matches (0–1).
    """

    entity_type: str
    pattern: str
    context_words: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=lambda: ["en"])
    score: float = 0.85


# ---------------------------------------------------------------------------
# Default entity types and confidence thresholds
# ---------------------------------------------------------------------------

_DEFAULT_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "LOCATION",
    "PASSPORT_NUMBER",
    "NATIONAL_ID",
    "DRIVERS_LICENSE",
    "CREDIT_CARD",
    "IBAN_CODE",
    "US_SSN",
    "DATE_OF_BIRTH",
]

# Per-entity minimum score for a span to be returned
_DEFAULT_THRESHOLDS: dict[str, float] = {
    "PERSON": 0.75,
    "EMAIL_ADDRESS": 0.85,
    "PHONE_NUMBER": 0.75,
    "LOCATION": 0.70,
    "PASSPORT_NUMBER": 0.80,
    "NATIONAL_ID": 0.80,
    "DRIVERS_LICENSE": 0.80,
    "CREDIT_CARD": 0.85,
    "IBAN_CODE": 0.85,
    "US_SSN": 0.85,
    "DATE_OF_BIRTH": 0.70,
    "MEDICAL_LICENSE": 0.80,
    "ORGANIZATION": 0.65,
}

# ---------------------------------------------------------------------------
# Regex patterns for the fallback detector
# ---------------------------------------------------------------------------

_REGEX_PATTERNS: list[tuple[str, str]] = [
    # Email
    ("EMAIL_ADDRESS", r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    # US phone (various formats)
    ("PHONE_NUMBER", r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
    # US SSN
    ("US_SSN", r"\b\d{3}-\d{2}-\d{4}\b"),
    # Credit card (Luhn-valid patterns — pattern only, no Luhn check)
    ("CREDIT_CARD", r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    # IBAN (2-letter country + 2 check digits + up to 30 alphanumeric)
    ("IBAN_CODE", r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b"),
    # Passport (generic: letter(s) + digits, 6–9 chars)
    ("PASSPORT_NUMBER", r"\b[A-Z]{1,2}[0-9]{6,9}\b"),
    # ISO date of birth context: "born" / "DOB" / "date of birth"
    ("DATE_OF_BIRTH", r"(?i)(?:born|dob|date of birth)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"),
    # US driver's licence (most states: letter + 7 digits)
    ("DRIVERS_LICENSE", r"\b[A-Z]\d{7}\b"),
]


# ---------------------------------------------------------------------------
# Main detector class
# ---------------------------------------------------------------------------


class PIIDetector:
    """
    Detect PII spans in text with optional Presidio backend.

    Parameters
    ----------
    entities:
        Entity types to detect.  Defaults to ``_DEFAULT_ENTITIES``.
    thresholds:
        Per-entity minimum confidence score.  Falls back to 0.75 for
        unlisted types.
    languages:
        Language codes to attempt detection for.  The Presidio backend
        will detect all listed languages; the regex fallback only supports
        ``"en"``.
    use_presidio:
        Force-enable or force-disable Presidio.  When ``None`` (default),
        Presidio is used if available; otherwise the regex fallback is used.
    """

    def __init__(
        self,
        entities: list[str] | None = None,
        thresholds: dict[str, float] | None = None,
        languages: list[str] | None = None,
        use_presidio: bool | None = None,
    ) -> None:
        self._entities = entities or _DEFAULT_ENTITIES
        self._thresholds = {**_DEFAULT_THRESHOLDS, **(thresholds or {})}
        self._languages = languages or ["en"]
        self._custom_recognizers: list[RegexPIIRecognizer] = []

        # Presidio availability
        if use_presidio is False:
            self._presidio_available = False
        else:
            self._presidio_available = self._check_presidio()

        self._presidio_analyzer: Any | None = None
        if self._presidio_available:
            self._presidio_analyzer = self._build_presidio_analyzer()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, text: str, language: str = "en") -> list[PIISpan]:
        """
        Detect PII spans in *text*.

        Parameters
        ----------
        text:
            Plain text to analyse.
        language:
            BCP-47 language code (used by Presidio backend; regex fallback
            always treats text as English).

        Returns
        -------
        list[PIISpan]
            Detected spans, sorted by ``start`` offset.
        """
        if not text:
            return []

        if self._presidio_available and self._presidio_analyzer:
            spans = self._detect_presidio(text, language)
        else:
            spans = self._detect_regex(text)

        # Apply custom recognizers on top
        for recognizer in self._custom_recognizers:
            if language in recognizer.languages:
                spans.extend(self._apply_regex_recognizer(text, recognizer, language))

        # Filter by threshold and sort
        spans = [s for s in spans if s.score >= self._thresholds.get(s.entity_type, 0.75)]
        spans.sort(key=lambda s: s.start)
        return self._deduplicate(spans)

    def add_recognizer(self, recognizer: RegexPIIRecognizer) -> None:
        """Register a custom regex-based entity recognizer."""
        self._custom_recognizers.append(recognizer)

    def set_threshold(self, entity_type: str, threshold: float) -> None:
        """Override the confidence threshold for a specific entity type."""
        self._thresholds[entity_type] = threshold

    @property
    def using_presidio(self) -> bool:
        """True when Presidio is active as the primary backend."""
        return self._presidio_available and self._presidio_analyzer is not None

    # ------------------------------------------------------------------
    # Internal — Presidio
    # ------------------------------------------------------------------

    @staticmethod
    def _check_presidio() -> bool:
        try:
            import presidio_analyzer  # noqa: F401

            return True
        except ImportError:
            return False

    def _build_presidio_analyzer(self) -> Any:
        from presidio_analyzer import AnalyzerEngine

        return AnalyzerEngine()

    def _detect_presidio(self, text: str, language: str) -> list[PIISpan]:
        results = self._presidio_analyzer.analyze(
            text=text,
            entities=self._entities,
            language=language,
        )
        spans = []
        for r in results:
            spans.append(
                PIISpan(
                    entity_type=r.entity_type,
                    start=r.start,
                    end=r.end,
                    score=r.score,
                    text=text[r.start : r.end],
                    language=language,
                )
            )
        return spans

    # ------------------------------------------------------------------
    # Internal — regex fallback
    # ------------------------------------------------------------------

    def _detect_regex(self, text: str) -> list[PIISpan]:
        spans: list[PIISpan] = []
        for entity_type, pattern in _REGEX_PATTERNS:
            if entity_type not in self._entities:
                continue
            for m in re.finditer(pattern, text):
                # For grouped patterns (DOB) the matched text may be in group 1
                start = m.start(1) if m.lastindex else m.start()
                end = m.end(1) if m.lastindex else m.end()
                spans.append(
                    PIISpan(
                        entity_type=entity_type,
                        start=start,
                        end=end,
                        score=0.80,
                        text=text[start:end],
                    )
                )
        return spans

    @staticmethod
    def _apply_regex_recognizer(
        text: str, recognizer: RegexPIIRecognizer, language: str
    ) -> list[PIISpan]:
        spans = []
        for m in re.finditer(recognizer.pattern, text):
            start = m.start(1) if m.lastindex else m.start()
            end = m.end(1) if m.lastindex else m.end()
            spans.append(
                PIISpan(
                    entity_type=recognizer.entity_type,
                    start=start,
                    end=end,
                    score=recognizer.score,
                    text=text[start:end],
                    language=language,
                )
            )
        return spans

    # ------------------------------------------------------------------
    # Internal — deduplication
    # ------------------------------------------------------------------

    @staticmethod
    def _deduplicate(spans: list[PIISpan]) -> list[PIISpan]:
        """
        Remove overlapping spans, keeping the one with the higher score.
        Spans must be sorted by start offset on entry.
        """
        result: list[PIISpan] = []
        for span in spans:
            if result and span.start < result[-1].end:
                # Overlap — keep the higher-confidence span
                if span.score > result[-1].score:
                    result[-1] = span
            else:
                result.append(span)
        return result
