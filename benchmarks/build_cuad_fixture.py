"""
Build benchmarks/fixtures/cuad_test.json.gz from the official CUAD v1 release.

    python -m benchmarks.build_cuad_fixture path/to/data.zip

data.zip: https://github.com/The-Atticus-Project/cuad/raw/main/data.zip
The zip is verified against its SHA-256 before use.  Only the official test
split (test.json: 102 contracts) is kept, reduced to contract text plus the
(category, start, end) of every gold answer span.

CUAD is published by The Atticus Project under CC BY 4.0 (dataset card:
https://huggingface.co/datasets/theatticusproject/cuad).  See
benchmarks/README.md for the attribution.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sys
import zipfile
from pathlib import Path

DATA_ZIP_SHA256 = "f8161d18bea4e9c05e78fa6dda61c19c846fb8087ea969c172753bc2f45b999a"
OUT = Path(__file__).parent / "fixtures" / "cuad_test.json.gz"


def build(zip_path: Path) -> dict:
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    if digest != DATA_ZIP_SHA256:
        raise SystemExit(f"data.zip SHA-256 mismatch: {digest}")
    with zipfile.ZipFile(zip_path) as zf:
        raw = json.loads(zf.read("test.json"))

    contracts = []
    for doc in raw["data"]:
        (para,) = doc["paragraphs"]
        text = para["context"]
        spans = []
        for qa in para["qas"]:
            category = qa["id"].rsplit("__", 1)[1]
            for ans in qa["answers"]:
                start = ans["answer_start"]
                end = start + len(ans["text"])
                assert text[start:end] == ans["text"]
                spans.append([category, start, end])
        spans.sort(key=lambda s: (s[1], s[2], s[0]))
        contracts.append({"title": doc["title"], "text": text, "spans": spans})
    contracts.sort(key=lambda c: c["title"])
    return {
        "source": "CUAD v1 test split (The Atticus Project, CC BY 4.0)",
        "data_zip_sha256": DATA_ZIP_SHA256,
        "contracts": contracts,
    }


def main() -> None:
    fixture = build(Path(sys.argv[1]))
    payload = json.dumps(fixture, ensure_ascii=False, separators=(",", ":")).encode()
    # mtime=0 so the gzip bytes are reproducible
    OUT.write_bytes(gzip.compress(payload, compresslevel=9, mtime=0))
    n = sum(len(c["spans"]) for c in fixture["contracts"])
    print(f"wrote {OUT} ({len(fixture['contracts'])} contracts, {n} spans)")


if __name__ == "__main__":
    main()
