# Architecture

ContractEx is organized as four discrete layers. Each layer can be used independently.

## The four layers

```
┌──────────────────────────────────────────────────────────────────┐
│  LAYER 3 · ANALYSIS          Risk · Obligations · Comparison     │
├──────────────────────────────────────────────────────────────────┤
│  LAYER 2 · EXTRACTION        LLM (scoped, schema-constrained)    │
├──────────────────────────────────────────────────────────────────┤
│  LAYER 1 · STRUCTURAL PARSE  Deterministic, zero LLM calls       │
├──────────────────────────────────────────────────────────────────┤
│  LAYER 0 · INGEST            Format-specific loaders             │
└──────────────────────────────────────────────────────────────────┘
```

### Layer 0 — Ingest (`contractex.loaders`)

Format-specific loaders convert raw files (PDF, DOCX, TXT) to plain text.
No parsing decisions are made here — the loaders are stateless converters.

### Layer 1 — Structural parse (`contractex.structure`)

The structural parser is entirely deterministic. It:

- Detects section headers using named regex patterns for all common legal numbering schemes
- Builds a section tree (sections, sub-sections, lettered sub-clauses)
- Extracts defined terms and their usages across the document
- Resolves cross-references and flags broken ones
- Detects signature blocks, schedules, recitals, and governing law hints

**Zero LLM calls.** Every decision is rule-based and auditable.

### Layer 2 — Extraction (`contractex.core.extractors`)

The LLM receives one structural unit at a time (never the whole document), together with:

- The clause text
- Its structural context (parent section title, sibling titles)
- Relevant defined terms from Layer 1

It returns structured JSON at `temperature=0`, validated by Pydantic schemas.
Every extraction result records which prompt versions produced it (`metadata.prompt_versions`).

### Layer 3 — Analysis (`contractex.analysis`)

Analysis operates on Layer 2 results — not raw documents. This means:

- You can run extraction once, cache the result, and run different analyses without re-invoking the LLM
- Playbook-based risk analysis is fully deterministic (keyword and regex matching)
- Obligation timelines and contract diffs require no LLM

## Module map

```
contractex/
├── loaders/          # Layer 0: format-specific ingest
├── structure/        # Layer 1: deterministic structural parse
│   ├── types.py      # DocumentStructure, Section, DefinedTerm, ...
│   ├── parser.py     # ContractStructureParser
│   ├── defined_terms.py
│   └── cross_refs.py
├── core/             # Layer 2: extraction
│   ├── extractors.py # ContractExtractor
│   ├── models.py     # Contract, Clause, Party, ...
│   └── classifiers.py
├── analysis/         # Layer 3: analysis (no LLM)
│   ├── risk.py       # RiskAnalyzer
│   ├── timeline.py   # ObligationTimeline
│   └── compare.py    # compare_contracts
├── playbooks/        # Versioned risk rule sets
├── eval/             # CUAD benchmark + calibration
├── llm/              # LLM provider adapters
└── privacy/          # PII detection + routing
```
