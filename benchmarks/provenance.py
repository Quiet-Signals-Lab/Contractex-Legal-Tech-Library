"""
Provenance on CUAD: does ProvenanceTracker resolve an extracted value to the
right place in the source document?

Each gold answer span stands in for a value an extractor returned.  Chunks come
from ClauseAwareChunker (CHUNK_SIZE tokens, OVERLAP tokens of overlap).  A
resolution is *correct* when the returned SourceSpan overlaps the gold span's
character range in the source; *exact* additionally requires
``source[span] == value``.

Modes:
* source_text — ``register_chunks(chunks, source_text=text)``
* legacy      — ``register_chunks(chunks)`` (offsets assume chunks tile the text)

Value variants, approximating what an LLM returns:
* verbatim   — the span text exactly as in the source
* whitespace — internal whitespace collapsed to single spaces
* lowercase  — whitespace collapsed and lower-cased
"""

from __future__ import annotations

import re
from typing import Any

from contractex.chunking import ClauseAwareChunker
from contractex.utils.provenance import ProvenanceTracker

CHUNK_SIZE = 512
OVERLAP = 50
_WS = re.compile(r"\s+")

VARIANTS = {
    "verbatim": lambda v: v,
    "whitespace": lambda v: _WS.sub(" ", v).strip(),
    "lowercase": lambda v: _WS.sub(" ", v).strip().lower(),
}


def run(contracts: list[dict[str, Any]]) -> dict[str, Any]:
    chunker = ClauseAwareChunker(max_chunk_size=CHUNK_SIZE, overlap=OVERLAP)
    counts: dict[str, dict[str, dict[str, int]]] = {
        mode: {v: {"values": 0, "resolved": 0, "correct": 0, "exact": 0} for v in VARIANTS}
        for mode in ("source_text", "legacy")
    }
    ambiguous = 0

    for contract in contracts:
        text = contract["text"]
        chunks = chunker.chunk(text)
        trackers = {"source_text": ProvenanceTracker(), "legacy": ProvenanceTracker()}
        trackers["source_text"].register_chunks(chunks, source_text=text)
        trackers["legacy"].register_chunks(chunks)

        for _category, start, end in contract["spans"]:
            gold = text[start:end]
            if not gold.strip():
                continue
            ambiguous += text.find(gold) != start
            for mode, tracker in trackers.items():
                for variant, transform in VARIANTS.items():
                    value = transform(gold)
                    c = counts[mode][variant]
                    c["values"] += 1
                    span = tracker.find_span(value)
                    if span is None or span.char_start is None or span.char_end is None:
                        continue
                    c["resolved"] += 1
                    c["correct"] += span.char_start < end and start < span.char_end
                    c["exact"] += text[span.char_start : span.char_end] == value

    return {
        "chunk_size": CHUNK_SIZE,
        "overlap": OVERLAP,
        "values_whose_text_occurs_earlier": ambiguous,
        "counts": counts,
    }
