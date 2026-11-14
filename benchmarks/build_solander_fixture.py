"""
Build benchmarks/fixtures/solander_en.json.gz from the Solander Detection Benchmark v1.2.

    python -m benchmarks.build_solander_fixture path/to/solander-benchmark-v1.2.zip

The zip (https://doi.org/10.5281/zenodo.23594288) is verified against its
SHA-256 before use.  Only the 980 English documents are kept, reduced to text,
genre, locale and the gold and mask spans, with offsets converted from the
bundle's UTF-16 units to Python string indices.  The dataset notice and its
canary string are kept with the documents.

The documents and labels are published under CC BY 4.0.  See
benchmarks/README.md for the attribution.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import zipfile
from pathlib import Path

BUNDLE_ZIP_SHA256 = "c5391bdf6b3f94995ab7242dfb2c4c5d75372ae92ba2c76ca35fbe78b60da3bb"
OUT = Path(__file__).parent / "fixtures" / "solander_en.json.gz"
CITATION = (
    "Hepburn, A. (2026). Solander Detection Benchmark v1.2, sealed synthetic track. "
    "Quiet Signals Lab. https://doi.org/10.5281/zenodo.23594288"
)


def python_index(text: str) -> dict[int, int]:
    """UTF-16 offset -> Python string index."""
    out, u = {}, 0
    for i, ch in enumerate(text):
        out[u] = i
        u += 2 if ord(ch) > 0xFFFF else 1
    out[u] = len(text)
    return out


def build(zip_path: Path) -> dict:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if digest != BUNDLE_ZIP_SHA256:
        raise SystemExit(f"bundle SHA-256 mismatch: {digest}")
    with zipfile.ZipFile(zip_path) as zf:
        head, *rows = (json.loads(line) for line in zf.read("documents.jsonl").splitlines())

    documents = []
    for row in rows:
        if row["lang"] != "en":
            continue
        text = row["text"]
        ix = python_index(text)
        documents.append(
            {
                "id": row["id"],
                "genre": row["genre"],
                "locale": row["locale"],
                "text": text,
                "spans": sorted([label, ix[a], ix[b]] for label, a, b in row["spans"]),
                "mask": sorted([label, ix[a], ix[b]] for label, a, b in row["mask"]),
            }
        )
    documents.sort(key=lambda d: d["id"])
    return {
        "source": CITATION,
        "licence": "CC BY 4.0 (documents and labels)",
        "notice": head["notice"],
        "canary": head["canary"],
        "bundle_zip_sha256": BUNDLE_ZIP_SHA256,
        "documents": documents,
    }


def main() -> None:
    fixture = build(Path(sys.argv[1]))
    payload = json.dumps(fixture, ensure_ascii=False, separators=(",", ":")).encode()
    # mtime=0 so the gzip bytes are reproducible
    OUT.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    print(f"wrote {OUT} ({len(fixture['documents'])} documents)")


if __name__ == "__main__":
    main()
