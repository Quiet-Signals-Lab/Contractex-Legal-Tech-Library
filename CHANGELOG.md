# Changelog

All notable changes to ContractEx will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/aahepburn/Contract-Clause-Extractor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aahepburn/Contract-Clause-Extractor/releases/tag/v0.1.0
