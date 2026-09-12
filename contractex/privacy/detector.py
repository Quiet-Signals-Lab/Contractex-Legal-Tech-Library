"""
PIIDetector — detects personally identifiable information in text.

Default backend: Microsoft Presidio (``pip install contractex[privacy]``).
Automatic fallback: regex-based detection when Presidio is not installed.

The regex fallback is intentionally conservative — it catches the most
common PII patterns without dependencies, so the privacy layer always
functions even in minimal installs.

Regex fallback limitations
--------------------------
* No PERSON, LOCATION, ORGANIZATION or NATIONAL_ID detection.  Names are the
  most common PII in contracts; install Presidio if names must be redacted.
* Phone, SSN and driver's licence patterns are US formats.  Credit cards are
  matched on shape only (no Luhn check); IBANs only without internal spaces.
* Dates of birth are matched only after "born", "DOB" or "date of birth".
* Zero-width/format characters, Unicode dashes, non-ASCII digits and
  non-Latin letters in email addresses are handled; other obfuscation
  (spelled-out digits, spacing out every character) is not.

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
import unicodedata
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

# Hyphen-minus plus the Unicode dashes that render the same (U+2010-2015,
# U+2212 minus, small/fullwidth hyphen-minus).  \d already matches any
# Unicode decimal digit, so fullwidth and other-script digits are covered.
_DASH = r"[-\u2010-\u2015\u2212\ufe58\ufe63\uff0d]"
_SEP = rf"(?:{_DASH}|[.\s])"

_REGEX_PATTERNS: list[tuple[str, str]] = [
    # Email (\w is Unicode-aware, so homoglyphs from other scripts are covered)
    ("EMAIL_ADDRESS", r"\b[\w.%+\-]+@[\w.\-]+\.[^\W\d_]{2,}\b"),
    # US phone (various formats)
    ("PHONE_NUMBER", rf"\b(?:\+?1{_SEP}?)?\(?\d{{3}}\)?{_SEP}?\d{{3}}{_SEP}?\d{{4}}\b"),
    # US SSN
    ("US_SSN", rf"\b\d{{3}}{_DASH}\d{{2}}{_DASH}\d{{4}}\b"),
    # Credit card (Luhn-valid patterns — pattern only, no Luhn check)
    ("CREDIT_CARD", rf"\b(?:\d{{4}}(?:{_DASH}|\s)?){{3}}\d{{4}}\b"),
    # IBAN (2-letter country + 2 check digits + up to 30 alphanumeric)
    ("IBAN_CODE", r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b"),
    # Passport (generic: letter(s) + digits, 6–9 chars)
    ("PASSPORT_NUMBER", r"\b[A-Z]{1,2}[0-9]{6,9}\b"),
    # ISO date of birth context: "born" / "DOB" / "date of birth"
    ("DATE_OF_BIRTH", r"(?i)(?:born|dob|date of birth)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})"),
    # US driver's licence (most states: letter + 7 digits)
    ("DRIVERS_LICENSE", r"\b[A-Z]\d{7}\b"),
]

# Regex matches carry no real confidence.  Score them at the highest default
# threshold so every built-in pattern survives default filtering; raising an
# entity's threshold above this value suppresses that pattern.
_REGEX_SCORE = max(_DEFAULT_THRESHOLDS.values())


def merge_overlapping(spans: list[PIISpan], text: str) -> list[PIISpan]:
    """
    Sort *spans* and merge any that overlap into their union.

    The merged span keeps the entity type of its highest-scoring member, so
    no character of any input span is left out of the result.
    """
    merged: list[PIISpan] = []
    for s in sorted(spans, key=lambda s: (s.start, -s.end)):
        prev = merged[-1] if merged else None
        if prev is not None and s.start < prev.end:
            end = max(prev.end, s.end)
            best = s if s.score > prev.score else prev
            merged[-1] = PIISpan(
                entity_type=best.entity_type,
                start=prev.start,
                end=end,
                score=best.score,
                text=text[prev.start : end],
                language=best.language,
            )
        else:
            merged.append(s)
    return merged


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

        self._presidio_analyzer: Any = None
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
            Non-overlapping spans, sorted by ``start`` offset, with offsets
            into *text*.
        """
        if not text:
            return []

        # Zero-width and other invisible format characters (Unicode category
        # Cf) can split a match.  Detect on a copy without them, then map the
        # offsets back so the returned spans cover the original characters.
        keep = [i for i, ch in enumerate(text) if unicodedata.category(ch) != "Cf"]
        view = "".join(text[i] for i in keep) if len(keep) < len(text) else text

        if self._presidio_available and self._presidio_analyzer:
            spans = self._detect_presidio(view, language)
        else:
            spans = self._detect_regex(view)

        # Apply custom recognizers on top
        for recognizer in self._custom_recognizers:
            if language in recognizer.languages:
                spans.extend(self._apply_regex_recognizer(view, recognizer, language))

        spans = [
            s
            for s in spans
            if s.end > s.start and s.score >= self._thresholds.get(s.entity_type, 0.75)
        ]
        if view is not text:
            for s in spans:
                s.start, s.end = keep[s.start], keep[s.end - 1] + 1
                s.text = text[s.start : s.end]
        return merge_overlapping(spans, text)

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
        assert self._presidio_analyzer is not None, "presidio analyzer not initialised"
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
                        score=_REGEX_SCORE,
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
