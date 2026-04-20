# ContractEx

ContractEx is a Python library for building contract analysis pipelines. It combines
deterministic structural parsing with schema-constrained LLM extraction so that every step
is auditable, and the probabilistic parts are narrow and measurable.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Layer 3 · Analysis         Risk · Obligations · Comparison      │
├──────────────────────────────────────────────────────────────────┤
│  Layer 2 · Extraction       LLM (scoped, schema-constrained)     │
├──────────────────────────────────────────────────────────────────┤
│  Layer 1 · Structural Parse Deterministic, fully testable        │
├──────────────────────────────────────────────────────────────────┤
│  Layer 0 · Ingest           Format-specific loaders              │
└──────────────────────────────────────────────────────────────────┘
```

Layer 1 and Layer 3 have **zero LLM calls** — they are fully auditable.

## Installation

```bash
pip install contractex
```

## Usage

```python
from contractex import ContractExtractor
from contractex.structure import parse_structure
from contractex.analysis import RiskAnalyzer
from contractex.playbooks import StandardNDAPlaybook

# Layer 1: deterministic structural parse — no LLM
structure = parse_structure(open("nda.txt").read())
print(structure.defined_terms)
print(structure.unresolved_refs)

# Layer 2: schema-constrained extraction
extractor = ContractExtractor(llm_provider_name="gpt-4o", confidence_threshold=0.75)
result = extractor.extract("nda.pdf")
print(result.clauses)

# Layer 3: playbook-based risk analysis — no LLM
analyzer = RiskAnalyzer(playbook=StandardNDAPlaybook())
risks = analyzer.analyze(result)
gaps = analyzer.missing_clauses(result)
```

## Next steps

- [Installation](getting-started/installation.md) — all install options and optional extras
- [Quick Start](getting-started/quickstart.md) — full pipeline walkthrough
