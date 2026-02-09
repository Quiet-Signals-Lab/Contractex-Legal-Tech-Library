# Changelog

All notable changes to ContractEx will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial package structure and core architecture
- Pydantic models for Contract, Party, Clause, FinancialTerm, RiskFlag
- Multi-LLM provider support (OpenAI, Anthropic, Local via Ollama)
- Document loaders for PDF and DOCX
- Clause-aware and semantic chunking strategies
- CUAD taxonomy with 41 clause types
- Risk analysis with rule-based and LLM approaches
- Export utilities (JSON, CSV, Excel)
- LangChain compatibility layer
- Batch processing support
- Confidence scoring and validation
- Comprehensive examples

### Changed
- Restructured from monolithic app to modular library
- Migrated from dataclasses to Pydantic v2 models
- Improved API design for simplicity and extensibility

## [0.1.0] - 2024-02-09

### Added
- Initial release of ContractEx library
- Core extraction functionality
- Basic documentation and examples

[Unreleased]: https://github.com/aahepburn/Contract-Clause-Extractor/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/aahepburn/Contract-Clause-Extractor/releases/tag/v0.1.0
