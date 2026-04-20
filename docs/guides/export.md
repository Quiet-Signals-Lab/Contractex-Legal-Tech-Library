# Export results

This guide covers the available output formats for ContractEx extraction results.

## Pydantic JSON

All ContractEx models are Pydantic v2 models and serialize to JSON out of the box:

```python
import json
from contractex import ContractExtractor

extractor = ContractExtractor(llm_provider_name="gpt-4o")
result = extractor.extract("contract.pdf")

# Serialize to JSON string
json_str = result.model_dump_json(indent=2)

# Or to a dict
data = result.model_dump()

# Save to file
with open("result.json", "w") as f:
    f.write(json_str)
```

## iCalendar (.ics) — obligation deadlines

```python
from contractex.analysis import ObligationTimeline

timeline = ObligationTimeline(
    obligations=result.obligations,
    effective_date="2024-01-01",
)

ics = timeline.to_ical()
with open("contract_deadlines.ics", "w") as f:
    f.write(ics)
```

Import the `.ics` file into Google Calendar, Outlook, or Apple Calendar.

## Playbook-based risk report

```python
from contractex.analysis import RiskAnalyzer
from contractex.playbooks import StandardNDAPlaybook

analyzer = RiskAnalyzer(playbook=StandardNDAPlaybook())
risks = analyzer.analyze(result)

for risk in risks:
    print(f"[{risk.severity.value.upper()}]  {risk.clause_ref}")
    print(f"  {risk.description}")
    if risk.recommended_language:
        print(f"  Suggested: {risk.recommended_language[:120]}")
    print()
```

## Contract diff

```python
from contractex.analysis import compare_contracts

diff = compare_contracts(result_v1, result_v2)
print(diff.summary())
```
