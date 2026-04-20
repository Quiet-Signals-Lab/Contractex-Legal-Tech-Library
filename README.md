# ContractEx

[![PyPI version](https://badge.fury.io/py/contractex.svg)](https://badge.fury.io/py/contractex)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Docs](https://readthedocs.org/projects/contractex/badge/?version=latest)](https://contractex.readthedocs.io)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

A Python library for building contract analysis pipelines.
Deterministic structural parsing → schema-constrained LLM extraction → playbook-based analysis.

**[Full documentation → contractex.readthedocs.io](https://contractex.readthedocs.io)**

```
Layer 3 · Analysis         Risk · Obligations · Comparison
Layer 2 · Extraction       LLM (scoped, schema-constrained)
Layer 1 · Structural Parse Deterministic, fully testable
Layer 0 · Ingest           Format-specific loaders
```

Layer 1 and Layer 3 have zero LLM calls. Privacy-first: the full pipeline runs locally with Llama 3.1.

## Install

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

# Layer 2: schema-constrained extraction
extractor = ContractExtractor(llm_provider_name="gpt-4o", confidence_threshold=0.75)
result = extractor.extract("nda.pdf")
print(result.clauses)

# Layer 3: playbook-based risk analysis — no LLM
analyzer = RiskAnalyzer(playbook=StandardNDAPlaybook())
risks = analyzer.analyze(result)
```

## Documentation

- [Installation & extras](https://contractex.readthedocs.io/getting-started/installation/)
- [Quick start](https://contractex.readthedocs.io/getting-started/quickstart/)
- [API reference](https://contractex.readthedocs.io/api/extractor/)
- [Architecture](https://contractex.readthedocs.io/explanation/architecture/)
- [Contributing](CONTRIBUTING.md)
