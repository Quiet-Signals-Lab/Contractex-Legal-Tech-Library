# Limitations

What Contractex does not do, or does only partly.  Stating these is part of
making the rest credible.  Where a limit is measured, the
[benchmarks](benchmarks.md) show by how much.

## Personal data detection

- **No names without Presidio.**  The regex fallback detects email addresses,
  US-format phone numbers, US Social Security numbers, card numbers (by shape;
  no Luhn check), IBANs without internal spaces, passport-style numbers, US
  driver's licence numbers, and dates of birth after "born", "DOB" or "date of
  birth".  It does not detect people, places, organisations or national
  identifiers.  In a `confidential` document those reach the model
  unredacted.  Install `contractex[privacy]` and a spaCy model to detect them.
- **Formats.**  International phone numbers, spaced IBANs and dates of birth
  written in words are not caught by the fallback.  Zero-width characters,
  Unicode dashes, fullwidth digits and non-Latin letters in email addresses
  are handled.
- **Labels can be wrong.**  A value that fits several patterns gets one label.
  A two-letter passport number, for example, is labelled `IBAN_CODE`.  It is
  still redacted.
- **Presidio itself is not benchmarked here**, and its detection depends on
  the spaCy model installed.

## Privacy enforcement

- The router trusts the document's profile.  Deciding sensitivity is up to
  you.
- `local_only` means "a `LocalProvider` instance".  The router does not check
  whether its Ollama host is actually on your machine.
- Only calls that go through the router are protected: the built-in tasks,
  `TaskPipeline`, `LegalRAGPipeline`, and code that uses `router.route()` or
  `router.guard()`.  Calling `ContractExtractor`, the analysers or a provider
  directly bypasses it.
- Streamed responses are redacted on the way out but not restored.
- A `REPLACE` redaction map contains the original values in plaintext.

## Documents

- PDFs are read from their text layer with PDFium.  Scanned PDFs have none:
  they need `contractex[ocr]` and the Tesseract program installed, and OCR
  quality limits everything after it.
- DOCX is read with python-docx.  Legacy `.doc` files are not supported.
- Layout (columns, tables) is flattened to text in reading order.

## Chunking and provenance

- Only the heading styles listed in [Chunking](guides/chunking.md) start a
  section.  Unnumbered capitalised headings and `WHEREAS` do not.
- Token counts are estimated as characters ÷ 4.
- `SemanticChunker` does not enforce its size limit on long paragraphs, and
  its chunks are not exact substrings of the source.
- Provenance resolves values found verbatim in the source.  Paraphrased or
  re-cased values usually do not resolve.  A value that appears more than once
  resolves to its first occurrence.
- `ContractExtractor` output does not carry source spans; run
  `ProvenanceTracker` over it.

## Tasks

- `summarization`, `timeline` and `obligations` read only the first 12,000
  characters of a document, and `comparison` the first 8,000 of each.  Longer
  documents are truncated silently.
- `classification` is keyword matching.
- Citation extraction covers US case citations, U.S.C., C.F.R., EU
  regulations and directives, and a few acronyms.  `CitationTask(use_llm=True)`
  currently has no effect.
- `risk_analysis` accepts a `severity_threshold` but does not apply it.
- `CUADBenchmark` in `contractex.eval` does not load the current CUAD release
  and is deprecated.  The maintained CUAD measurements are in
  [`benchmarks/`](benchmarks.md).

## Models and providers

- The Anthropic extra is pinned below SDK 1.0; see
  [LLM providers](guides/providers.md#known-issues).
- The Google provider is not tested against the live API in this repository.
- Cost estimates use price tables from 2024.
- Model output varies between runs.  Accuracy per provider, and downstream
  extraction accuracy, are not yet measured in the benchmarks.

## Benchmarks

- The CUAD measurements cover 102 English-language commercial contracts from
  US SEC filings.  Other document types, jurisdictions and languages are not
  covered.
- The privacy detection fixture is small and synthetic; it shows which formats
  are handled, not recall on real documents.

## Retrieval and storage

- `LegalRAGPipeline` keeps its vectors in memory and embeds with
  sentence-transformers (`contractex[rag]`).
- The Postgres repository (`contractex[storage]`) writes the original
  `documents`/`clauses` schema.  `schema_v2.sql` has no Python API yet.
- The knowledge graph (`contractex[graph]`) has no tests.
