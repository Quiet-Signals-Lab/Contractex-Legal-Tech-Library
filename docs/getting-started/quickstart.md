# Quick Start

This page walks through the three-layer ContractEx pipeline end to end.

## Layer 1: Structural parse (no LLM)

```python
from contractex.structure import parse_structure

text = open("nda.txt").read()
structure = parse_structure(text)

# Inspect the section tree
for section in structure.iter_all_sections():
    print(section.number, section.title)

# Defined terms resolved without any LLM call
print(structure.defined_terms["Confidential Information"])

# Catch broken cross-references before extraction
print(structure.unresolved_refs)
```

## Layer 2: Extraction

```python
from contractex import ContractExtractor

extractor = ContractExtractor(
    llm_provider_name="gpt-4o",
    confidence_threshold=0.75,
)
result = extractor.extract("nda.pdf")

print(result.parties)
print(result.clauses)

# Prompt provenance
print(result.metadata.prompt_versions)
```

## Layer 3: Analysis (no LLM)

```python
from contractex.analysis import RiskAnalyzer
from contractex.playbooks import StandardNDAPlaybook

analyzer = RiskAnalyzer(playbook=StandardNDAPlaybook())
risks = analyzer.analyze(result)
gaps = analyzer.missing_clauses(result)

for risk in risks:
    print(f"[{risk.severity.value.upper()}] {risk.description}")
```

## Next steps

- [Run extraction locally with Ollama](../guides/local-llm.md)
- [Write a custom playbook](../guides/playbooks.md)
- [API Reference — ContractExtractor](../api/extractor.md)
