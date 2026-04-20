# Write a custom playbook

This guide explains how to create, compose, and load custom playbooks for your practice area.

## What is a playbook?

A playbook defines:

- **Required clauses** — clause types that must appear in the contract (any that are absent become gaps)
- **Risk rules** — pattern-based checks that flag problematic language

Playbooks have no LLM dependency. All matching is deterministic keyword and regex matching.

## Use a built-in playbook

```python
from contractex.playbooks import StandardNDAPlaybook, SaaSPlaybook

nda = StandardNDAPlaybook()
saas = SaaSPlaybook()
```

## Write a YAML playbook

Save this as `my_msa_playbook.yaml`:

```yaml
name: "My MSA Playbook"
version: "1.0"
description: "Master Services Agreement risk rules."
required_clauses:
  - governing_law
  - cap_on_liability
  - data_security
  - dispute_resolution
rules:
  - id: "msa.liability.no_cap"
    clause_type: "cap_on_liability"
    description: "No liability cap — critical risk."
    severity: "critical"
    recommended_language: |
      Each party's aggregate liability shall not exceed the fees paid
      or payable in the twelve months preceding the claim.
    flag_if_missing: true

  - id: "msa.data.no_breach_notification"
    clause_type: "data_security"
    description: "No data breach notification timeline."
    severity: "high"
    required_keywords: ["72 hours", "48 hours", "notify", "notification"]
    flag_if_missing: true
```

Load it:

```python
from contractex.playbooks import Playbook

custom = Playbook.from_yaml_file("my_msa_playbook.yaml")
```

## Subclass a built-in playbook

```python
from contractex.playbooks import StandardNDAPlaybook, PlaybookRule, RiskSeverity

class MyNDAPlaybook(StandardNDAPlaybook):
    def __init__(self):
        super().__init__()
        self.version = "1.1"
        self.rules.append(PlaybookRule(
            id="nda.jurisdiction.must_be_delaware",
            clause_type="governing_law",
            description="Governing law must be Delaware.",
            severity=RiskSeverity.HIGH,
            required_keywords=["Delaware"],
        ))
```

## Run analysis

```python
from contractex.analysis import RiskAnalyzer

analyzer = RiskAnalyzer(playbook=MyNDAPlaybook())
risks = analyzer.analyze(result)
gaps = analyzer.missing_clauses(result)
```
