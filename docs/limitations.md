# Limitations

What Contractex does not do, or does only partly.  Stating these is part of
making the rest credible.  Where a limit is measured, the
[benchmarks](benchmarks.md) show by how much.

## Personal data detection

- **No names without Presidio.**  The built-in patterns detect email
  addresses, US-format phone numbers, US Social Security numbers, card numbers
  (by shape; no Luhn check), IBANs without internal spaces, passport-style
  numbers, US driver's licence numbers, and dates of birth after "born", "DOB"
  or "date of birth".  They do not detect people, places, organisations or
  national identifiers.  In a `confidential` document those reach the model
  unredacted.  Install `contractex[privacy]` and a spaCy model to detect
  people and places.
- **No national identifiers with either backend** (BSN, NINO, SIN and so on).
  Add a `RegexPIIRecognizer` for the ones you handle.
- **Formats.**  International phone numbers, spaced IBANs and dates of birth
  written in words are not caught.  Presidio finds some international phone
  numbers but scores them below the detector's threshold; lowering it also
  lets through false matches such as four-digit numbers.  Zero-width
  characters, Unicode dashes, fullwidth digits and non-Latin letters in email
  addresses are handled.
- **Labels can be wrong.**  A value that fits several patterns gets one label.
  A two-letter passport number, for example, is labelled `IBAN_CODE`.  It is
  still redacted.
- **Presidio itself is not benchmarked here**, and its detection depends on
  the spaCy model installed.  The test suite checks, against the real engine,
  that identifiers the patterns catch are still caught with Presidio on.

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
- `PrivacyProfile` carries `redaction_strategy`, `retention_days`,
  `data_subject_ids` and `consent_reference`.  They are stored with the
  document and enforce nothing: the router redacts with the strategy of its
  own `PIIRedactor`, and nothing deletes a document when its retention period
  ends.

## Documents

- PDFs are read from their text layer with PDFium.  Scanned PDFs have none:
  they need `contractex[ocr]` and the Tesseract program installed, and OCR
  quality limits everything after it.
- DOCX is read with python-docx.  Legacy `.doc` files are not supported.
- Layout (columns, tables) is flattened to text in reading order.
- `URLLoader` and `APILoader` fetch the URL you give them, private addresses
  included: if the URL comes from a user, check it first.  They refuse a
  redirect or pagination link from a public host to a private address, and
  any redirect to another host when the request carries credentials.  The
  host name is resolved for that check and again for the request, so a DNS
  answer that changes in between is not caught.

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
- Dates and amounts the model returns are normalised only when unambiguous.
  An all-numeric date that could be day-first or month-first (`05/03/2024`),
  a two-digit year, or text with several unmarked numbers gives `None`.

## Tasks

- `summarization`, `timeline` and `obligations` read only the first 12,000
  characters of a document, and `comparison` the first 8,000 of each.  Longer
  documents are truncated silently.
- `classification` is keyword matching.
- Citation extraction covers US case citations, U.S.C., C.F.R., EU
  regulations and directives, and a few acronyms.  `CitationTask(use_llm=True)`
  currently has no effect.
- `risk_analysis` accepts a `severity_threshold` but does not apply it.  If
  its model call fails, it returns the rule-based results with a log line and
  no other signal.
- `ObligationTimeline` resolves only deadlines counted from the effective
  date.  Business days, and periods counted from another event ("after
  termination"), are left unresolved.
- `CUADBenchmark` in `contractex.eval` does not load the current CUAD release
  and is deprecated.  The maintained CUAD measurements are in
  [`benchmarks/`](benchmarks.md).

## Models and providers

- The Anthropic extra is pinned below SDK 1.0; see
  [LLM providers](guides/providers.md#known-issues).
- The Google provider is not tested against the live API in this repository.
- Cost estimates use price tables from 2024.
- `AnthropicProvider` estimates tokens as characters ÷ 4: the exact count is an
  API request that would carry the text.
- `LocalProvider` does not set Ollama's context size (`num_ctx`).  A prompt
  longer than the model's configured window is truncated by Ollama without an
  error.
- Provider constructors accept `temperature=` and do not use it; pass it per
  call.
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
- `sync_sources()` re-fetches every URL in full; it does not use conditional
  requests.
- Conflict detection compares metadata (dates, jurisdiction, authority), not
  what the sources say.  A jurisdiction or authority difference is still
  presented to the model as conflicting positions.
- The Postgres repository (`contractex[storage]`) writes the original
  `documents`/`clauses` schema.  `schema_v2.sql` has no Python API yet.
- The knowledge graph (`contractex[graph]`) has no tests.
