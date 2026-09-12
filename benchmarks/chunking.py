"""
Chunk integrity on CUAD: how often does a gold clause span land wholly inside
a single chunk?

A span split across two chunks is the failure the clause-aware chunker exists
to prevent: an extraction prompt sees half a provision, and a citation resolves
to a fragment.  This suite needs no LLM and is fully deterministic.

Chunkers compared, at each size in SIZES (tokens, estimated as chars // 4),
all with overlap 0:

* clause_aware  — contractex ClauseAwareChunker
* semantic      — contractex SemanticChunker (paragraph mode)
* fixed_window  — baseline: consecutive windows of the same size, cut at the
                  last whitespace before the limit (defined here, not shipped)

Only spans that could fit in one chunk (length <= size * 4 chars) are scored;
longer spans are counted separately.
"""

from __future__ import annotations

import bisect
import re
from collections import defaultdict
from typing import Any

from contractex.chunking import ClauseAwareChunker, SemanticChunker
from contractex.chunking.base import ChunkingStrategy

SIZES = [256, 512, 1024, 2048]
BREAKDOWN_SIZE = 512
LENGTH_BUCKETS = [(0, 200), (200, 1000), (1000, 4000), (4000, 10**9)]

_PIECES = re.compile(r"\S+|\s+")
_WS = re.compile(r"\s+")


class FixedWindowChunker(ChunkingStrategy):
    """Baseline: fixed-size windows cut at whitespace, ignoring document structure."""

    def __init__(self, max_chunk_size: int) -> None:
        self.max_chunk_size = max_chunk_size

    def chunk(self, text: str) -> list[str]:
        out, a, n, step = [], 0, len(text), self.max_chunk_size * 4
        while a < n:
            b = min(n, a + step)
            if b < n:
                cut = max(text.rfind(" ", a, b), text.rfind("\n", a, b))
                if cut > a:
                    b = cut
            piece = text[a:b].strip()
            if piece:
                out.append(piece)
            a = b
        return out


CHUNKERS: dict[str, Any] = {
    "clause_aware": lambda size: ClauseAwareChunker(max_chunk_size=size, overlap=0),
    "semantic": lambda size: SemanticChunker(max_chunk_size=size, overlap=0),
    "fixed_window": FixedWindowChunker,
}


def normalised(text: str) -> tuple[str, list[int]]:
    """Text with whitespace runs collapsed to one space, and each char's source index."""
    out: list[str] = []
    index: list[int] = []
    for m in _PIECES.finditer(text):
        if m.group().isspace():
            out.append(" ")
            index.append(m.start())
        else:
            out.append(m.group())
            index.extend(range(m.start(), m.end()))
    return "".join(out), index


def locate(norm: str, index: list[int], chunks: list[str]) -> list[tuple[int, int]] | None:
    """Source [start, end) of each chunk, ignoring whitespace differences; None if one is missing."""
    spans, cursor = [], 0
    for c in chunks:
        nc = _WS.sub(" ", c).strip()
        j = norm.find(nc, cursor)
        if j < 0:
            return None
        spans.append((index[j], index[j + len(nc) - 1] + 1))
        cursor = j + len(nc)
    return spans


def trimmed(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def run(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    by_length: dict[str, list[list[int]]] = {}
    by_category: dict[str, dict[str, list[int]]] = {}
    failure_reasons: dict[str, dict[str, int]] = {}

    prepared = [(c, *normalised(c["text"])) for c in contracts]

    for name, make in CHUNKERS.items():
        for size in SIZES:
            chunker = make(size)
            fit = contained = too_long = n_chunks = over = unlocatable = 0
            tokens: list[int] = []
            lengths = [[0, 0] for _ in LENGTH_BUCKETS]
            cats: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            reasons: dict[str, int] = defaultdict(int)
            heading_regex = getattr(chunker, "section_regex", None)
            for contract, norm, index in prepared:
                text = contract["text"]
                chunks = chunker.chunk(text)
                spans = locate(norm, index, chunks)
                if spans is None:
                    unlocatable += 1
                    continue
                n_chunks += len(chunks)
                for c in chunks:
                    t = len(c) // 4
                    tokens.append(t)
                    over += t > size
                starts = [s for s, _ in spans]
                heads = [m.start() for m in heading_regex.finditer(text)] if heading_regex else []
                for category, s0, e0 in contract["spans"]:
                    s, e = trimmed(text, s0, e0)
                    if e - s > size * 4:
                        too_long += 1
                        continue
                    i = bisect.bisect_right(starts, s) - 1
                    ok = i >= 0 and spans[i][0] <= s and e <= spans[i][1]
                    fit += 1
                    contained += ok
                    if not ok and heads:
                        j = bisect.bisect_right(heads, s)
                        if j < len(heads) and heads[j] < e:
                            reasons["span contains a heading; split there by design"] += 1
                        elif e - s > size * 2:
                            reasons["span longer than half the chunk budget"] += 1
                        else:
                            reasons["size limit split a section inside the span"] += 1
                    bucket = next(
                        k for k, (lo, hi) in enumerate(LENGTH_BUCKETS) if lo <= e - s < hi
                    )
                    lengths[bucket][0] += ok
                    lengths[bucket][1] += 1
                    cats[category][0] += ok
                    cats[category][1] += 1
            rows.append(
                {
                    "chunker": name,
                    "size": size,
                    "spans_scored": fit,
                    "spans_intact": contained,
                    "integrity": round(contained / fit, 4) if fit else None,
                    "spans_longer_than_chunk": too_long,
                    "chunks": n_chunks,
                    "mean_chunk_tokens": round(sum(tokens) / len(tokens), 1) if tokens else 0,
                    "chunks_over_size": over,
                    "contracts_unlocatable": unlocatable,
                }
            )
            if size == BREAKDOWN_SIZE:
                by_length[name] = lengths
                by_category[name] = dict(cats)
                if reasons:
                    failure_reasons[name] = dict(sorted(reasons.items()))

    return {
        "sizes": SIZES,
        "rows": rows,
        "breakdown_size": BREAKDOWN_SIZE,
        "length_buckets": LENGTH_BUCKETS,
        "by_length": by_length,
        "by_category": by_category,
        "failure_reasons": failure_reasons,
    }
