"""Clause-aware chunking that preserves clause boundaries."""

from __future__ import annotations

import re

from contractex.chunking.base import ChunkingStrategy
from contractex.exceptions import ChunkingError

_SENTENCE_GAP = re.compile(r"(?<=[.!?])\s+")
_PARAGRAPH_GAP = re.compile(r"\n[ \t]*\n")
_WHITESPACE = re.compile(r"\s+")

Span = tuple[int, int]


class ClauseAwareChunker(ChunkingStrategy):
    """
    Clause-aware chunking strategy that tries to keep legal clauses intact.

    The text is cut into sections at heading lines (see ``SECTION_PATTERNS``);
    with no headings it is cut at blank lines.  Consecutive sections are packed
    into chunks of at most ``max_chunk_size`` tokens (``count_tokens``).  A
    section too large on its own is split at sentence boundaries, and a
    sentence too large on its own at word boundaries.

    Guarantees:

    * every chunk is an exact substring of the input, so ``text.find(chunk)``
      recovers its character offset;
    * no chunk exceeds ``max_chunk_size`` tokens;
    * chunks never start or end mid-word (except a single word longer than
      ``max_chunk_size``, which is cut);
    * a heading stays in the same chunk as the start of its body;
    * with ``overlap > 0``, each chunk after the first begins with up to
      ``overlap`` tokens from the end of the previous chunk, starting at a
      sentence (or failing that, word) boundary, when that still fits.
    """

    # Line starts that open a new section (leading whitespace is allowed)
    SECTION_PATTERNS = [
        r"\d+\.(?:\d+\.?)*[ \t]*[A-Z(\"'“‘]",  # 1. Term / 2.1 Term / 1.1 "Affiliate"
        r"(?i:article)\s+\d+",  # Article 1
        r"(?i:section)\s+\d+",  # Section 1
        r"\([a-zA-Z]\)",  # (a) subsection
        r"\([0-9]+\)",  # (1) subsection
        r"\w+\s+TERMINATION",  # EARLY TERMINATION
    ]

    def __init__(
        self,
        max_chunk_size: int = 4000,
        overlap: int = 200,
        preserve_sentences: bool = True,
    ):
        """
        Initialize clause-aware chunker.

        Args:
            max_chunk_size: Maximum size of each chunk in tokens
            overlap: Number of tokens to overlap between chunks
            preserve_sentences: Split oversized sections at sentence boundaries
                (otherwise at word boundaries only)
        """
        self.max_chunk_size = max_chunk_size
        self.overlap = overlap
        self.preserve_sentences = preserve_sentences

        self.section_regex = re.compile(
            r"^[ \t]*(?:" + "|".join(self.SECTION_PATTERNS) + ")", re.MULTILINE
        )

    def chunk(self, text: str) -> list[str]:
        """
        Split text into chunks while preserving clause boundaries.

        Args:
            text: Full document text

        Returns:
            List of text chunks, each a substring of *text*
        """
        try:
            return [text[a:b] for a, b in self._chunk_spans(text)]
        except Exception as e:
            raise ChunkingError(f"Chunking failed: {str(e)}") from e

    # ------------------------------------------------------------------
    # Internals — all positions are offsets into the original text
    # ------------------------------------------------------------------

    def _fits(self, text: str, a: int, b: int) -> bool:
        return self.count_tokens(text[a:b]) <= self.max_chunk_size

    def _chunk_spans(self, text: str) -> list[Span]:
        spans: list[Span] = []
        current: Span | None = None
        for s, e in self._section_spans(text):
            if current and self._fits(text, current[0], e):
                current = (current[0], e)
                continue
            if current:
                spans.append(current)
            if self._fits(text, s, e):
                current = (self._overlap_start(text, spans, s, e), e)
            else:
                spans.extend(self._split_large(text, s, e))
                current = None
        if current:
            spans.append(current)
        return spans

    def _section_spans(self, text: str) -> list[Span]:
        bounds = sorted({0, *(m.start() for m in self.section_regex.finditer(text))})
        if len(bounds) <= 1:
            bounds = [0, *(m.end() for m in _PARAGRAPH_GAP.finditer(text))]
        return _stripped(text, bounds)

    def _overlap_start(self, text: str, spans: list[Span], s: int, e: int) -> int:
        """Start *s* earlier to repeat the tail of the previous chunk, if it fits."""
        if not self.overlap or not spans:
            return s
        prev_start, prev_end = spans[-1]
        lo = max(prev_start, prev_end - self.overlap * 4)
        window = text[lo:prev_end]
        gap = _SENTENCE_GAP.search(window) or _WHITESPACE.search(window)
        if gap is None or not self._fits(text, lo + gap.end(), e):
            return s
        return lo + gap.end()

    def _split_large(self, text: str, s: int, e: int) -> list[Span]:
        """Split a section that exceeds max_chunk_size on its own."""
        if not self.preserve_sentences:
            return self._split_words(text, s, e)
        bounds = [s, *(s + m.end() for m in _SENTENCE_GAP.finditer(text[s:e]))]
        out: list[Span] = []
        current: Span | None = None
        for a, b in _stripped(text, bounds, e):
            if current and self._fits(text, current[0], b):
                current = (current[0], b)
            elif self._fits(text, a, b):
                if current:
                    out.append(current)
                current = (a, b)
            else:
                # Too large on its own: split at words, carrying any pending
                # short run (e.g. the section heading) into the first piece.
                out.extend(self._split_words(text, current[0] if current else a, b))
                current = None
        if current:
            out.append(current)
        return out

    def _split_words(self, text: str, s: int, e: int) -> list[Span]:
        """Cut [s, e) at whitespace into pieces that each fit."""
        out: list[Span] = []
        a = s
        while a < e:
            b = min(e, a + self.max_chunk_size * 4 + 3)
            while not self._fits(text, a, b):  # count_tokens may be overridden
                b -= max(1, (b - a) // 10)
            if b < e and not text[b].isspace():
                cut = _last_whitespace(text, a, b)
                if cut > a:
                    b = cut
            out.append((a, b))
            a = b
            while a < e and text[a].isspace():
                a += 1
        return [(a, b) for a, b in out if a < b]


def _stripped(text: str, bounds: list[int], end: int | None = None) -> list[Span]:
    """Spans between consecutive bounds, trimmed of whitespace, empty ones dropped."""
    out: list[Span] = []
    for a, b in zip(bounds, [*bounds[1:], len(text) if end is None else end], strict=True):
        while a < b and text[a].isspace():
            a += 1
        while b > a and text[b - 1].isspace():
            b -= 1
        if a < b:
            out.append((a, b))
    return out


def _last_whitespace(text: str, a: int, b: int) -> int:
    """Index of the last whitespace character in text[a:b], or -1."""
    for i in range(b - 1, a, -1):
        if text[i].isspace():
            return i
    return -1
