# Run extraction locally with Ollama

This guide shows how to run the full ContractEx pipeline without sending any data to a cloud provider.

Layer 1 (structural parse) and Layer 3 (analysis) have no LLM dependency at all — they always run
locally. This guide covers Layer 2, the extraction step.

## Install Ollama

Download and install Ollama from [https://ollama.com](https://ollama.com), then pull a model:

```bash
ollama pull llama3.1:8b
```

## Install ContractEx with local extras

```bash
pip install "contractex[local]"
```

## Run extraction

```python
from contractex import ContractExtractor

extractor = ContractExtractor(
    llm_provider_name="ollama/llama3.1:8b",
    confidence_threshold=0.70,  # slightly lower for 8B models
)

result = extractor.extract("sensitive_contract.pdf")
print(result.parties)
print(result.clauses)
```

No API keys, no internet connection, no data egress.

## Model recommendations

| Model | Notes |
|---|---|
| `llama3.1:8b` | Best balance of speed and accuracy for local use |
| `llama3.1:70b` | Near cloud quality; requires ≥48 GB RAM |
| `mistral:7b` | Faster but weaker at structured JSON output |
