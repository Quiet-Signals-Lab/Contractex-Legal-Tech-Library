# Installation

Contractex needs Python 3.11 or newer (tested on 3.11 to 3.14).

```bash
pip install contractex
```

This installs the core: `pydantic`, `pypdfium2` (PDF text, BSD-3-Clause /
Apache-2.0), `python-docx` and `pyyaml`.  With the core alone you can parse
documents and their structure, detect and redact personal data with the regex
fallback, chunk, trace provenance, run the deterministic tasks and the
evaluation harness.  Nothing in the core talks to a network service.

## Choose your setup

**Keeping documents on your machine** (a local model through Ollama):

```bash
pip install "contractex[ollama,privacy]"
python -m spacy download en_core_web_lg   # model used by Presidio for names
ollama pull llama3.1:8b                    # or any model from ollama.com/library
```

[Ollama](https://ollama.com) must be running.  Set `OLLAMA_HOST` if it is not
at `http://localhost:11434`.

**Using a hosted model** (OpenAI, Anthropic or Google):

```bash
pip install "contractex[openai]"        # or [anthropic] or [google]
export OPENAI_API_KEY=...                # or ANTHROPIC_API_KEY / GOOGLE_API_KEY
```

Add `privacy` to redact names from `confidential` documents before they are
sent.  See [LLM providers](../guides/providers.md) for the details of each
provider.

## All extras

| Extra | Installs | For |
|---|---|---|
| `openai`, `anthropic`, `google`, `ollama`, `langchain` | the vendor SDK | calling that provider |
| `privacy` | `presidio-analyzer`, `cryptography` | name, place and ID detection; `ENCRYPT` redaction.  Also download a spaCy model. |
| `ocr` | `pytesseract`, `pillow` | scanned PDFs.  Also install the Tesseract program. |
| `network` | `requests` | loading documents from URLs and JSON APIs |
| `export` | `pandas`, `openpyxl` | DataFrame, CSV and Excel export |
| `spacy` | `spacy` | the `ner` task.  Also download a spaCy model. |
| `storage` | `psycopg2-binary`, `pgvector` | PostgreSQL persistence.  Needs PostgreSQL with the `pgvector` extension. |
| `rag` | `sentence-transformers` | `LegalRAGPipeline` embeddings (downloads a model on first use) |
| `graph` | `networkx`, `neo4j`, `rdflib` | the knowledge graph |
| `all` | every extra above | |

## From source

```bash
git clone https://github.com/Quiet-Signals-Lab/Contractex-Legal-Tech-Library.git
cd Contractex-Legal-Tech-Library
pip install -e ".[dev]"
pytest
python -m benchmarks --check
```

See [Contributing](../project/contributing.md) for the checks CI runs.
