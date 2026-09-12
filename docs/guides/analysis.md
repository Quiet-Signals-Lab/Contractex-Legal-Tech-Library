# Contract analysis

Three steps, only one of which calls a model:

1. **Structure** (no model): sections, defined terms, cross-references,
   recitals and a governing-law hint, from deterministic parsing.
2. **Extraction** (model): `ContractExtractor` produces a typed `Contract`
   with parties, clauses, financial terms and risks.
3. **Playbook review** (no model): keyword rules and required-clause checks
   over the extracted clauses.

## Structure

```python
from textwrap import shorten

from contractex.structure import parse_structure

text = open("examples/data/sample_nda.txt", encoding="utf-8").read()
structure = parse_structure(text)

term = structure.defined_terms["Confidential Information"]
print(term.definition_section, "|", shorten(term.definition_text, 60))
print([(ref.raw_text, ref.resolved) for ref in structure.cross_references])
print(structure.governing_law_hint, "|", shorten(structure.recitals[0], 50))
```

```text
1 | any non-public information disclosed by one party to [...]
[('Section 4', True), ('Section 2', True), ('Section 9', False)]
Delaware | the parties wish to explore a possible data- [...]
```

`governing_law_hint` is a regular-expression signal.  It misses phrasings
such as "Delaware law governs this Agreement"; the
[evaluation guide](evaluation.md) measures exactly that.

## Extraction

`ContractExtractor` loads a document (PDF, DOCX or text) or takes text
directly, chunks it with `ClauseAwareChunker`, and makes schema-constrained
model calls.  Document details come from the first two chunks, capped at
12,000 characters.  Clauses and financial terms come from one call per chunk.
Risks come from keyword rules plus one call over the first 20,000 characters.
It needs a provider, and it has no document privacy profile.  Pass a
[guarded provider](privacy.md#where-it-is-enforced), or use the
`contract_extraction` [task](tasks.md), which does that for you.

```python
from contractex import ContractExtractor
from contractex.llm import LocalProvider

extractor = ContractExtractor(llm_provider=LocalProvider(model="llama3.1:8b"), confidence_threshold=0.7)
contract = extractor.extract("examples/data/sample_nda.txt")
print(type(contract).__name__, contract.metadata.filename)
```

```text
Contract sample_nda.txt
```

What the model returns is not shown here.  Items below `confidence_threshold`
are kept and listed in `contract.metadata.warnings`, never silently dropped.

## Playbook review

A playbook lists required clause types and rules.  `RiskAnalyzer` runs it
over extracted clauses; here two clauses are built by hand, to show the
deterministic part on its own:

```python
from contractex.analysis import RiskAnalyzer
from contractex.core.models import Clause, Contract
from contractex.playbooks import StandardNDAPlaybook

extracted = Contract(
    clauses=[
        Clause(
            clause_type="confidentiality",
            section_number="2",
            text="Each party shall keep the other party's Confidential Information secret "
            "and use it only for the Purpose.",
        ),
        Clause(
            clause_type="governing_law",
            section_number="6",
            text="This Agreement is governed by the laws of the State of Delaware.",
        ),
    ]
)

analyzer = RiskAnalyzer(playbook=StandardNDAPlaybook())
for flag in analyzer.analyze(extracted):
    print(flag.severity.value, flag.playbook_rule, "section", flag.clause_ref)
print("Missing:", analyzer.missing_clauses(extracted))
```

```text
medium nda.scope.overly_broad section 2
medium nda.return_of_info.missing section 2
Missing: ['termination_for_cause', 'effective_date', 'expiration_date']
```

Rules are keyword checks on each clause.  The `overly_broad` flag fires
because clause 2 contains no carve-out wording, even though this NDA puts its
carve-outs in Section 4.  Treat flags as prompts for review, not findings.
`SaaSPlaybook` is also built in.  Playbooks round-trip to YAML with
`Playbook.to_yaml()` and `Playbook.from_yaml()`.

## Export

`Contract` is a Pydantic model: `contract.model_dump_json()` gives JSON.
`contract.to_dataframe()` and `contract.to_excel(path)` need
`contractex[export]`.

```python
print(extracted.model_dump_json(include={"clauses": {0: {"clause_type", "section_number"}}}))
```

```text
{"clauses":[{"clause_type":"confidentiality","section_number":"2"}]}
```
