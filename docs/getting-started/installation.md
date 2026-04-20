# Installation

Install ContractEx and its dependencies using pip.

```bash
pip install contractex
```

## From source

Clone the repository and install in editable mode:

```bash
git clone https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library.git
cd Contractex-Legal-Tech-Library
pip install -e "."
```

## Optional extras

```bash
pip install "contractex[local]"     # Ollama local LLM support
pip install "contractex[privacy]"   # PII detection and redaction
pip install "contractex[eval,datasets]"  # CUAD benchmark support
pip install "contractex[all]"       # Everything
```

## Cloud LLM API keys

```bash
export OPENAI_API_KEY=sk-...
export ANTHROPIC_API_KEY=sk-ant-...
export GOOGLE_API_KEY=...
```

No API keys are required if you use a local model via Ollama.
See [Run extraction locally with Ollama](../guides/local-llm.md).
