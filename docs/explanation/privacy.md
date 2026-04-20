# Why Local-First

ContractEx is designed so the full pipeline can run with no data leaving your machine.

## The privacy constraint

Contracts contain material non-public information: deal terms, counterparty identities, price,
indemnities, governing law. Sending this to a third-party API carries legal and commercial risk —
regardless of the API provider's privacy policy.

ContractEx treats local execution as the primary path, not an afterthought.

## What runs locally without any configuration

**Layer 1 (structural parse)** and **Layer 3 (analysis)** have no LLM dependency at all.
They run on your machine, use no network, and process at native Python speed.

## Layer 2 local options

For extraction (Layer 2), you can choose a local model via [Ollama](https://ollama.com):

```bash
ollama pull llama3.1:8b
pip install "contractex[local]"
```

```python
from contractex import ContractExtractor

extractor = ContractExtractor(llm_provider_name="ollama/llama3.1:8b")
result = extractor.extract("sensitive_contract.pdf")
```

Zero API keys. Zero data egress.

## The PrivacyProfile routing system

For teams that use a mix of local and cloud models, ContractEx includes a routing system based
on document sensitivity:

| Sensitivity | LLM routing |
|---|---|
| `public` | any provider |
| `confidential` | any provider + auto-redact PII |
| `restricted` | local-only |
| `secret` | blocked entirely |

```python
from contractex.privacy import PrivacyProfile

profile = PrivacyProfile(sensitivity="restricted")
# ContractExtractor will refuse to route to a cloud provider
```

Install privacy extras: `pip install "contractex[privacy]"`

## Trade-offs

Local 8B models are weaker than GPT-4o at structured extraction. Expect lower F1 on CUAD
(~0.73 vs ~0.83). For most clause types, the gap is manageable. For high-stakes clauses
(limitation of liability, indemnification), consider using a larger local model or accepting
the confidence-threshold filter (`confidence_threshold=0.70`).
