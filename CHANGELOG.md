# Changelog

All notable changes to ContractEx will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-04-20

### Added

#### Authority taxonomy — `contractex.taxonomy.authority`

- `AuthorityLevel` `IntEnum` covering thirteen levels from `CONSTITUTIONAL` (100) through `BLOG_NEWS` (5) and `UNKNOWN` (1), with `normalised` property mapping to `[0.01, 1.00]`, `label`, and `is_binding()` predicate
- `AuthorityProfile` Pydantic model with `authority_weight` property (10 % of normalised level when superseded), `is_superseded` / `superseded_by` fields, `for_level()` class method, and optional `JurisdictionTag` attachment

#### Structured jurisdiction model — `contractex.taxonomy.jurisdiction`

- `JurisdictionTag` Pydantic model replacing flat `jurisdiction: str`; ISO 3166-1 alpha-2 country codes, optional region and court system, `applicability` literal (`binding` / `persuasive` / `informational`)
- `is_broader_than()`, `conflicts_with()` (same country, different region → conflict signal), and `matches()` (hard-filter helper for RAG) methods
- `from_string()` class method parses `"US-CA"`, `"DE-Federal"`, `"EU"`, etc.; backward-compatible `__str__`

#### RAG conflict detection — `contractex.rag.conflict`

- `ConflictType` enum: `JURISDICTION_CONFLICT`, `AUTHORITY_CONFLICT`, `TEMPORAL_CONFLICT`, `UNSETTLED_QUESTION`
- `Conflict` Pydantic model with `severity` field (`high` / `medium` / `low`)
- `ConflictDetector` — exhaustive pairwise comparison across retrieved source docs; `detect(docs, query)` returns all conflicts; `build_conflict_prompt_addendum(conflicts)` appends structured warning to RAG prompts, preventing false-consensus summarisation

#### RAG pipeline enhancements — `contractex.rag.pipeline`

- `LegalRAGPipeline` constructor: `alpha` / `beta` / `gamma` blending weights (defaults `0.60` / `0.30` / `0.10`) and optional `conflict_detector` (created automatically by default)
- `ingest()` now writes `authority_weight`, `publication_year`, `jurisdiction_country`, `jurisdiction_region`, and `is_superseded` into vector-store metadata; stores `LegalDoc` in an internal registry for conflict detection
- `query()` new `jurisdiction_filter: JurisdictionTag | None` parameter: hard-filters mismatched jurisdictions and superseded sources; applies `α·semantic + β·authority + γ·recency` weighted rescoring; runs `ConflictDetector` and appends conflict addendum to the LLM prompt; returns `RAGResponse` with `conflicts` and `authority_range` populated
- `_stream_query()` threads `conflicts`, `authority_range`, and `source_docs` through every yielded partial response
- `RAGResponse` two new fields: `conflicts: list[Conflict]`, `authority_range: tuple[float, float]`
- `contractex.rag` exports: `Conflict`, `ConflictType`, `ConflictDetector`

#### LLM streaming — `contractex.llm`

- `BaseLLMProvider.stream_complete()` default implementation (single-chunk fallback) and `stream_complete_async()` async wrapper
- `OpenAIProvider.stream_complete()` — native streaming via OpenAI `stream=True`
- `AnthropicProvider.stream_complete()` — native streaming via `client.messages.stream()` context manager

#### Privacy eval harness — `contractex.eval`

- `EvalCase` three new fields: `expected_pii_entities`, `should_be_blocked`, `expected_redaction_count`
- `PrivacyCaseResult` — per-case PII precision / recall / F1, blocking correctness, redaction count accuracy
- `PrivacyMetrics` — suite-level aggregate with `report()`, `assert_min_pii_recall()`, `assert_perfect_blocking()`
- `EvalHarness.run_privacy()` — extractor-agnostic runner accepting `pii_detector_fn`, `redactor_fn`, `router_fn`

#### Storage

- `contractex/storage/schema_v2.sql` — PostgreSQL schema v2: `legal_docs`, `extracted_fields`, `document_chunks` (pgvector), `audit_log`; `clauses` backward-compat VIEW; `gdpr_erase_document()` PL/pgSQL function using HMAC-SHA256 pseudonymisation
- `contractex/storage/migrations/v1_to_v2.sql` — transactional migration with guard, archive preservation, and full index + trigger recreation

#### Package extras

- `privacy` — `presidio-analyzer`, `presidio-anonymizer`, `cryptography`
- `rag` — `sentence-transformers`
- `graph` — `networkx`, `neo4j`
- `stream` — no extra deps (marker for streaming-capable installs)
- `all` updated to include all new extras

### Changed

- `LegalDoc` gains `jurisdiction_tag: JurisdictionTag | None` and `authority_profile: AuthorityProfile | None` fields alongside the existing `jurisdiction: str | None` (backward compatible); computed properties `effective_jurisdiction_tag` and `authority_weight`
- `contractex/taxonomy/__init__.py` now exports `JurisdictionTag`, `AuthorityLevel`, `AuthorityProfile`

## [0.2.0] - 2026-04-20 — released to PyPI

### Added

#### Network source adapters — `contractex.loaders.source_adapter`

- `SourceAdapter` — abstract base extending `DocumentLoader` with ETag/Last-Modified change detection, exponential-backoff retry, and SHA-256 content hashing
- `URLLoader` — fetches arbitrary HTTP/HTTPS URLs; strips HTML via stdlib parser; delegates PDF URLs to PyMuPDF; supports conditional GET (304 Not Modified)
- `APILoader` — fetches JSON REST APIs; extracts text via dot-path (`"data.opinion.text"`); handles RFC 5988 Link-header and JSON `next`-key pagination; supports Bearer/API-key auth
- `FetchCache` / `FetchResult` dataclasses for provenance-aware fetch state

#### General legal document model — `contractex.core.legal_document`

- `DocType` enum covering statutes, regulations, case opinions, identity documents, government forms, contracts, pleadings, correspondence
- `SourceSpan` — precise field provenance: chunk ID, source URL, page, character offsets, snippet (auto-truncated to 300 chars)
- `LegalDocumentMetadata` — fetch provenance (ETag, Last-Modified, retrieval timestamp, content hash) plus processing metadata
- `LegalDocument` — general-purpose extraction model with `extracted_fields`, `field_confidences`, `provenance` dict, `set_field()` / `add_provenance()` helpers, `provenance_coverage` property, and JSON/dict serialisation

#### Provenance tracking — `contractex.utils.provenance`

- `ChunkRecord` — dataclass with deterministic chunk ID (index + 8-char content hash), global character offsets, page number
- `ProvenanceTracker` — registers text chunks and resolves extracted values back to `SourceSpan` objects; two-pass resolution: exact substring O(n) then Jaccard token-overlap fallback; `annotate()` / `annotate_all()` one-liner helpers; `coverage()` statistics

#### Audit logging — `contractex.utils.audit`

- `AuditEventType` taxonomy: `document_ingested`, `document_loaded`, `fields_extracted`, `field_rejected`, `review_requested`, `review_completed`, `document_deleted`, `access_denied`, `pipeline_error`
- `AuditEvent` — Pydantic model with auto-UUID, UTC timestamp, per-field arrays, confidence score, flexible metadata
- `NullAuditBackend` — no-op sink for testing
- `JSONLAuditBackend` — append-only newline-delimited JSON; thread-safe via `threading.Lock`; auto-creates parent directories; `read_all()` class method for inspection
- `PostgresAuditBackend` — writes to `audit_log` table; `autocommit` mode; auto-DDL on first use; thread-safe
- `AuditLogger` — thread-safe facade with `log_ingestion()`, `log_extraction()`, `log_review_request()`, `log_review_completion()`, `log_deletion()`, `log_error()` convenience methods; backend failures are re-emitted via standard `logging` — never raised to callers; factory methods `from_jsonl()`, `from_postgres()`, `null()`

#### Confidence routing — `contractex.utils.routing`

- `RoutingDecision` enum: `AUTO_ACCEPT`, `HUMAN_REVIEW`, `AUTO_REJECT`
- `ReviewItem` — single routed field with decision, reason, confidence, and optional `SourceSpan`
- `RoutingResult` — bucketed outcome with `accepted` dict, `review_queue` (sorted by confidence ascending), `rejected` list; `needs_review`, `fully_accepted`, `acceptance_rate`, `review_field_names`, `rejected_field_names` properties; `summary()` string
- `ConfidenceRouter` — global and per-field threshold overrides; `route_field()`, `route_document(LegalDocument)`, `route_dict()` interfaces

#### Eval harness — `contractex.eval`

- `EvalCase` — labeled test case with `input_path` / `input_text`, `expected_fields`, `field_weights`, tags
- `EvalSuite` — named collection with YAML (`from_yaml()`) and JSON (`from_json()`) loaders, `filter_by_tag()` / `filter_by_doc_type()` helpers
- `FieldResult` — pass/fail with weighted score per field; case-insensitive string comparison; strict bool equality
- `CaseResult` — per-case aggregate with `score_ratio`, `passed`, `failed_fields`
- `ExtractionMetrics` — suite-level aggregate with `field_accuracy` (weighted), `case_accuracy`, per-field stats table; `assert_min_field_accuracy()` / `assert_min_case_accuracy()` for pytest CI gates; `report()` formatted summary
- `EvalHarness` — extractor-agnostic runner accepting any `(EvalCase) -> dict` callable; `fail_fast` mode; error capture; per-case timing

#### Infrastructure

- `contractex.utils.__init__` exports all new utilities
- `contractex.core.__init__` exports `LegalDocument`, `LegalDocumentMetadata`, `DocType`, `SourceSpan`
- `contractex.__init__` top-level exports for `ProvenanceTracker`, `ConfidenceRouter`, `AuditLogger`, `LegalDocument`, `DocType`, `SourceSpan`
- `pyproject.toml` new optional extras: `network` (requests), `eval` (pyyaml)
- 198 unit tests across 6 new test files; all network calls mocked; no database required

## [0.1.1] - 2026-02-13

### Added

- Google Gemini LLM provider (`GoogleProvider`) with support for gemini-2.0-flash, gemini-2.5-pro, and other Gemini models
- Plain text document loader (`TextLoader`) for .txt files with automatic encoding detection
- Support for .txt files in `AutoLoader` for simplified contract loading

## [0.1.0] - 2026-02-13

### Added

- Full LLM extraction pipeline (`_extract_from_chunks`) supporting OpenAI, Anthropic, and local Ollama models
- Multi-phase extraction: contract metadata + parties (Phase 1), clause + financial per-chunk (Phase 2), deduplication (Phase 3)
- CUAD taxonomy with 41 clause types embedded in prompt templates for accurate LLM classification
- Exponential-backoff retry logic in all three LLM providers (rate limits, network errors, 5xx responses)
- `ContractExtractor.estimate_extraction_cost()` for pre-flight cost/token estimation with per-phase breakdown
- LLM-based risk analysis wired into `RiskAnalyzer` alongside existing keyword rule engine
- Internal Pydantic schemas (`LLMContractInfoResponse`, `LLMClausesResponse`, etc.) bridging LLM output to public models
- Parallel chunk processing via `ThreadPoolExecutor` (up to 4 workers)
- Graceful degradation: per-chunk LLM failures add warnings to `ContractMetadata` without crashing
- Pydantic models for Contract, Party, Clause, FinancialTerm, RiskFlag, ContractMetadata
- Storage layer with PostgreSQL + pgvector
- Hybrid clause retrieval with Reciprocal Rank Fusion reranking
- Document loaders for PDF and DOCX
- Clause-aware and semantic chunking strategies
- Export utilities (JSON, CSV, Excel)
- LangChain compatibility layer
- Batch processing and async extraction support
- Confidence scoring and validation
- Comprehensive examples (basic, advanced, batch, local LLM, FastAPI, storage, NER, datasets)
- CI/CD with GitHub Actions (tests, type checking, linting, PyPI publish workflow)
- `CONTRIBUTING.md` with dev setup and contribution guidelines

[Unreleased]: https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/compare/v0.1.1...v0.2.0
[0.1.1]: https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/compare/v0.1.0...v0.1.1
[0.1.0]: https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library/releases/tag/v0.1.0
