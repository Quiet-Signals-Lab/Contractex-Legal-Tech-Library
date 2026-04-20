# Design Decisions

Key design choices made in ContractEx and the reasoning behind them.

## Deterministic logic wrapping probabilistic model behaviour

The core principle: every decision that *can* be made deterministically *is* made deterministically.

The LLM is scoped to two tasks where determinism is genuinely insufficient:
1. Clause classification (which CUAD type does this text belong to?)
2. Slot-filling (extract the governing law jurisdiction from this clause text)

Everything else — section boundary detection, defined terms, cross-references, risk scoring — is rule-based.

## Why Layer 1 must have zero LLM calls

If the structural parser is wrong, you need to know *exactly* what it received and *exactly* which rule
produced the wrong output. LLMs don't provide that. Deterministic code does.

This also means Layer 1 is fully unit-testable: input text in, `DocumentStructure` out, no mocking.

## One structural unit per LLM call

The LLM never sees the full contract. It sees one section at a time. This:

- Reduces hallucination (less context = fewer irrelevant associations)
- Makes failures localized (a bad extraction for Section 4.2 doesn't contaminate Section 7)
- Makes prompt engineering tractable (you're reasoning about one clause, not the whole document)

## Prompt versioning as provenance

Every extraction result records `metadata.prompt_versions` — a dict mapping prompt names to their
version strings. This means you can answer: *"did the extraction quality change between deploys?"*
without guessing whether a prompt was modified.

## Playbooks are data, not code

Risk rules are serializable to YAML so that lawyers and compliance officers can review and modify
them without touching Python. The YAML schema is documented in `contractex/playbooks/schema.yaml`.

## No application code in the library

ContractEx is a library, not an application. It does not include:

- A web server or REST API (users implement their own with FastAPI, Flask, etc.)
- A CLI tool
- A database schema that it manages on your behalf

This keeps the dependency surface small and makes ContractEx composable with whatever infrastructure
you already have.
