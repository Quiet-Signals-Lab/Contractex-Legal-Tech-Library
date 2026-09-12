# Benchmarks

Deterministic measurements of three claims the library makes, run against
committed fixtures with one command.  No network, no API keys, no LLM calls.

```bash
pip install -e ".[dev]"
python -m benchmarks           # regenerate results/results.json and results/summary.md
python -m benchmarks --check   # fail if the committed results differ from a fresh run
```

**Results: [results/summary.md](results/summary.md).**  Every number there is
produced by the command above; CI runs `--check` so the committed results
cannot drift from the code.  This page describes method and limits only and
deliberately repeats no results.

| Suite | Claim under test | Data |
|---|---|---|
| [chunking.py](chunking.py) | Clause-aware chunking keeps clauses in one chunk more often than structure-blind splitting | CUAD test split |
| [provenance.py](provenance.py) | `ProvenanceTracker` resolves an extracted value to where it came from | CUAD test split |
| [privacy.py](privacy.py) | The regex PII fallback catches the formats it claims; `secret` documents never reach a provider; `restricted` documents reach only a `LocalProvider` | Synthetic fixture |

Not measured yet: extraction accuracy downstream of chunking, and accuracy
per LLM provider (cloud versus local).  Both need model calls and are
postponed.  Presidio-backed PII detection is not measured either: the privacy
suite runs the regex fallback only.

## Data

**CUAD v1 test split** — [fixtures/cuad_test.json.gz](fixtures/cuad_test.json.gz):
all 102 contracts of the official test split and their 2,643 gold answer spans,
reduced to contract text plus `(category, start, end)` per span.  Rebuild it
from the official release with
`python -m benchmarks.build_cuad_fixture path/to/data.zip`; the builder checks
the zip's SHA-256 and the output is byte-for-byte reproducible.

**Synthetic PII fixture** — [fixtures/privacy_cases.jsonl](fixtures/privacy_cases.jsonl):
128 contract-style sentences, each with one planted value and several non-PII
distractors.  Values are fictitious (`.test` domains, 555-01xx phone numbers,
published test card and IBAN numbers).  Rebuild with
`python -m benchmarks.privacy build`.

## Method

### Chunk integrity

Each contract is chunked by `ClauseAwareChunker`, `SemanticChunker` (paragraph
mode) and `fixed_window`, a structure-blind baseline defined in `chunking.py`
that cuts consecutive windows at the last whitespace before the size limit.
All run at 256, 512, 1024 and 2048 tokens with overlap 0.  A gold span is
*intact* when it lies wholly inside one chunk.  Chunks are mapped back to
source offsets ignoring whitespace differences, because `SemanticChunker`
re-joins paragraphs.  Spans longer than a chunk can hold are excluded from
that size's score and counted separately.

The summary also breaks results down by span length and CUAD category,
lists every category where the clause-aware chunker does not beat both
baselines, and classifies why it splits the spans it does split.

### Provenance

Each gold span stands in for a value an extractor returned.  Chunks come from
`ClauseAwareChunker` (512 tokens, overlap 50) and are registered with
`ProvenanceTracker` in two modes: with `source_text` (offsets located in the
document) and without it (the tracker's older behaviour, which assumes chunks
tile the document).  Each value is looked up verbatim, with whitespace
collapsed, and lower-cased — approximations of how an LLM returns text.  A
resolution is *correct* when the returned span overlaps the gold span, and
*exact* when the source text at the returned offsets equals the value.

### Privacy

*Detection*: `PIIDetector(use_presidio=False)` runs on every case.  A planted
value is *caught* when every letter and digit of it is inside a detected
span, so nothing identifying survives redaction.  Cases are grouped by
variant: plain, obfuscated (zero-width characters, Unicode dashes, fullwidth
digits, Cyrillic homoglyphs), and *unsupported* — formats the fallback is not
designed for (names, addresses, international phone numbers, spaced IBANs,
dates of birth in words), included so the limits appear in the results.  A
distractor is a false positive when any detected span overlaps it.
`EvalHarness.run_privacy()` also reports entity-type recall and precision.

*Routing*: every sensitivity level × {cloud provider, `LocalProvider`} × entry
point (`PrivacyAwareLLMRouter`, `TaskPipeline`, the comparison task's second
document, `LegalRAGPipeline`).  Providers are stubs that record every prompt.
A cell passes when the outcome matches the policy — blocked, rejected,
excluded from context, sent redacted, or sent unchanged — and the stub never
received text it must not see.  `EvalHarness.run_privacy()` reports blocking
accuracy on the same policy.

## Limitations

- **CUAD is one corpus.**  102 English-language commercial contracts drawn
  from SEC EDGAR filings, annotated for CUAD's categories (40 of its 41
  categories have answers in the test split).  Other document types,
  jurisdictions, languages and scanned documents are not covered.
- **Tokens are estimated** as characters ÷ 4, the library's own estimate, not
  a model tokenizer.
- **Integrity is a proxy.**  It shows whether an extraction prompt could see
  a whole clause, not whether the extraction is right.  Clause-aware chunking
  produces more, smaller chunks than fixed windows at the same limit, which
  means more model calls; the summary reports chunk counts so this cost is
  visible.  `SemanticChunker` exceeds its size limit on some chunks, which
  favours it on integrity.
- **Only overlap 0** is measured for chunking.
- **Gold spans are not LLM output.**  Real extractions paraphrase more than the
  three variants tested, so provenance on real output will be lower.  When a
  value occurs more than once in a contract, the tracker returns the first
  occurrence.
- **The privacy fixture is small, synthetic and written for this suite.**
  Its results show which formats the fallback handles; they are not an
  estimate of recall on real documents.  Only the regex fallback is measured.
- **The routing matrix uses stub providers.**  It verifies the library's
  enforcement logic, not network behaviour, and it trusts any `LocalProvider`
  regardless of the host it points at, as the router does.

## Licensing and attribution

The CUAD fixture is derived from the Contract Understanding Atticus Dataset
(CUAD) v1 by The Atticus Project, licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) (licence as declared
on the [dataset card](https://huggingface.co/datasets/theatticusproject/cuad)).
Changes: only the test split is kept, reduced to contract text and answer-span
offsets.  Dataset: <https://www.atticusprojectai.org/cuad>.  Paper: Hendrycks,
Burns, Chen and Ball, *CUAD: An Expert-Annotated NLP Dataset for Legal
Contract Review*, [arXiv:2103.06268](https://arxiv.org/abs/2103.06268).

The synthetic privacy fixture and all benchmark code are part of this
repository and licensed Apache-2.0.
