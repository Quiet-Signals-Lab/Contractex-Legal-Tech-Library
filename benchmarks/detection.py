"""
Personal data left after redaction, on 980 labelled English documents.

    python -m benchmarks.detection           # regenerate results/detection.json
    python -m benchmarks.detection --check   # exit 1 if it differs from a fresh run

Needs the privacy extra and spaCy's ``en_core_web_lg`` model, the one
Presidio loads by default; the versions measured are recorded in the result.
Afterwards run ``python -m benchmarks`` to refresh summary.md and the README.

Each document is redacted the way the router redacts a ``confidential``
prompt: ``PIIDetector()`` with its defaults, every detected span replaced.
The arms differ only in whether Presidio runs next to the built-in patterns.
A labelled token is *left* when any of its characters is outside every
detected span.  The tokens of a label are its identifying words: capitalised
words and words with a digit, without titles such as "Mr" (the rule of the
dataset's own scorer, score.py, MIT).

The dataset labels people, places, organisations, addresses, reference
numbers, dates, amounts and occupations, but not email addresses or phone
numbers.  A *false positive* is therefore a detected person or place that
overlaps no labelled span.  Detections of the types the dataset does not label
are counted separately: they are mostly real personal data, such as the
email address of a named person.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import logging
import re
import sys
from importlib import metadata
from pathlib import Path
from typing import Any

from contractex.privacy import PIIDetector

HERE = Path(__file__).parent
FIXTURE = HERE / "fixtures" / "solander_en.json.gz"
RESULTS = HERE / "results" / "detection.json"

# Person names, postal addresses, reference numbers (accounts, cases,
# policies), places, organisations
SCORED = ("PER", "ADDR", "REF", "LOC", "ORG")
# Detected types the dataset labels (as PER, and LOC or ADDR)
LABELLED_TYPES = {"PERSON", "LOCATION"}
TITLES = {
    "mr", "mr.", "mrs", "mrs.", "ms", "ms.", "dr", "dr.", "sir", "dame", "prof", "prof.",
    "professor", "judge", "justice", "kc", "qc", "esq.",
}  # fmt: skip
TOKEN = re.compile(r"[^\s,;]+")
STRIP = ".'’\"()[]"


def load_fixture() -> dict[str, Any]:
    fixture: dict[str, Any] = json.loads(gzip.decompress(FIXTURE.read_bytes()))
    return fixture


def identifying(text: str, start: int, end: int, label: str) -> list[tuple[int, int]]:
    """Character ranges of the identifying tokens of a labelled span."""
    out = []
    for m in TOKEN.finditer(text, start, end):
        tok = m.group(0)
        core = tok.strip(STRIP)
        lead = len(tok) - len(tok.lstrip(STRIP))
        if not core or (label == "PER" and tok.lower() in TITLES):
            continue
        if core[0].isupper() or core[0].isdigit():
            out.append((m.start() + lead, m.start() + lead + len(core)))
    return out


def score(documents: list[dict[str, Any]], detector: PIIDetector) -> dict[str, Any]:
    left = {label: [0, 0] for label in SCORED}  # [tokens left, tokens]
    false_positives = 0
    unlabelled: dict[str, int] = {}
    for doc in documents:
        text = doc["text"]
        detected = detector.detect(text, language="en")
        covered = bytearray(len(text))
        for s in detected:
            covered[s.start : s.end] = b"\x01" * (s.end - s.start)
        for label, start, end in doc["spans"]:
            if label in left:
                for a, b in identifying(text, start, end, label):
                    left[label][0] += not all(covered[a:b])
                    left[label][1] += 1
        labelled = doc["spans"] + doc["mask"]
        for s in detected:
            if any(s.start < e and a < s.end for _, a, e in labelled):
                continue
            if s.entity_type in LABELLED_TYPES:
                false_positives += 1
            else:
                unlabelled[s.entity_type] = unlabelled.get(s.entity_type, 0) + 1
    return {
        "tokens_left": left,
        "false_positives": false_positives,
        "unlabelled_type_detections": unlabelled,
    }


def versions() -> dict[str, str]:
    return {
        name: metadata.version(name) for name in ("presidio-analyzer", "spacy", "en-core-web-lg")
    }


def run() -> dict[str, Any]:
    fixture = load_fixture()
    documents = fixture["documents"]
    with_presidio = PIIDetector(use_presidio=True)
    return {
        "source": fixture["source"],
        "fixture_sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        "documents": len(documents),
        "words": sum(len(d["text"].split()) for d in documents),
        "versions": versions(),
        "arms": {
            "patterns": score(documents, PIIDetector(use_presidio=False)),
            "presidio": score(documents, with_presidio),
        },
    }


def main() -> int:
    logging.disable(logging.WARNING)
    fresh = json.dumps(run(), indent=1, sort_keys=True) + "\n"
    if "--check" in sys.argv:
        if not RESULTS.exists() or RESULTS.read_text(encoding="utf-8") != fresh:
            print(f"stale detection results: {RESULTS.name}; run python -m benchmarks.detection")
            return 1
        print("detection results are up to date")
        return 0
    RESULTS.write_text(fresh, encoding="utf-8")
    print(f"wrote {RESULTS}; now run python -m benchmarks to refresh the summary and README")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
