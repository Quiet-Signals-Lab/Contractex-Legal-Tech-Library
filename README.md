# ContractEx — Legal Document Intelligence for Python

[![PyPI version](https://badge.fury.io/py/contractex.svg)](https://badge.fury.io/py/contractex)
[![PyPI Downloads](https://img.shields.io/pypi/dm/contractex)](https://pypistats.org/packages/contractex)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

ContractEx is a production-ready Python library for LLM-powered legal document intelligence. It provides a composable pipeline of loaders, chunkers, extractors, and post-processing utilities that work on both **bilateral contracts** (NDAs, MSAs, SOWs) and **general legal documents** (statutes, regulations, case opinions, identity documents).

The library is designed to be the shared foundation for two distinct product categories:

| Use-case | What ContractEx provides |
| --- | --- |
| **Legal RAG chatbot** — query over statutes, regulations, case law | Loaders (URL/API), chunkers, LLM providers, provenance tracking, eval harness |
| **IDP / document automation** — extract passport fields, fill government forms | Pydantic extraction schemas, confidence routing, audit logging, eval harness |

---

## Contents

- [Architecture overview](#architecture-overview)
- [Module map](#module-map)
- [Installation](#installation)
- [Quick start](#quick-start)
- [Contract extraction pipeline](#contract-extraction-pipeline)
- [General legal document pipeline](#general-legal-document-pipeline)
- [Network loaders](#network-loaders)
- [Provenance tracking](#provenance-tracking)
- [Confidence routing](#confidence-routing)
- [Audit logging](#audit-logging)
- [Eval harness](#eval-harness)
- [Storage layer](#storage-layer)
- [LLM providers](#llm-providers)
- [Examples](#examples)
- [Development](#development)

---

## Architecture overview

ContractEx is structured as a layered pipeline. Each layer can be used independently or composed into a full pipeline.

```mermaid
graph TB
    subgraph Sources["Source Layer"]
        F[File<br/>PDF · DOCX · TXT]
        U[URL<br/>HTML · PDF · plain text]
        A[API<br/>JSON REST · paginated]
    end

    subgraph Loaders["Loaders  contractex.loaders"]
        AL[AutoLoader]
        PL[PDFLoader]
        DL[DOCXLoader]
        TL[TextLoader]
        SA[SourceAdapter<br/>URLLoader · APILoader]
    end

    subgraph Chunking["Chunking  contractex.chunking"]
        CA[ClauseAwareChunker]
        SC[SemanticChunker]
    end

    subgraph LLM["LLM Providers  contractex.llm"]
        OA[OpenAIProvider]
        AN[AnthropicProvider]
        GG[GoogleProvider]
        LC[LocalProvider<br/>Ollama]
    end

    subgraph Core["Extraction  contractex.core"]
        CE[ContractExtractor]
        LD[LegalDocument]
        PT[ProvenanceTracker]
    end

    subgraph PostProc["Post-processing  contractex.utils"]
        CR[ConfidenceRouter]
        AU[AuditLogger]
    end

    subgraph Storage["Storage  contractex.storage"]
        PG[(PostgreSQL<br/>pgvector)]
    end

    subgraph Eval["Eval  contractex.eval"]
        EH[EvalHarness]
        ES[EvalSuite]
        EM[ExtractionMetrics]
    end

    F --> AL --> Chunking
    U --> SA --> Chunking
    A --> SA --> Chunking
    Chunking --> LLM --> Core
    Core --> PostProc
    PostProc --> Storage
    Core --> Eval
```

---

## Module map

```text
contractex/
├── loaders/
│   ├── base.py              # DocumentLoader ABC
│   ├── auto.py              # AutoLoader — extension-based dispatch
│   ├── pdf.py               # PDFLoader  (PyMuPDF)
│   ├── docx.py              # DOCXLoader (python-docx)
│   ├── text.py              # TextLoader (plain text + encoding detection)
│   ├── source_adapter.py    # SourceAdapter · URLLoader · APILoader  ← NEW
│   └── langchain_compat.py  # LangChain adapter
│
├── chunking/
│   ├── base.py              # ChunkingStrategy ABC
│   ├── clause_aware.py      # Splits on legal section boundaries
│   └── semantic.py          # Splits on semantic similarity
│
├── llm/
│   ├── base.py              # LLMProvider ABC
│   ├── openai_provider.py   # GPT-4o
│   ├── anthropic_provider.py# Claude 3.x
│   ├── google_provider.py   # Gemini 2.x
│   └── local_provider.py    # Ollama (Llama, Mistral, Phi …)
│
├── core/
│   ├── models.py            # Contract · Clause · Party · FinancialTerm · RiskFlag
│   ├── legal_document.py    # LegalDocument · DocType · SourceSpan  ← NEW
│   ├── extractors.py        # ContractExtractor (multi-phase orchestrator)
│   ├── analyzers.py         # RiskAnalyzer
│   ├── classifiers.py       # CUADClassifier (41 clause types)
│   ├── extraction_schemas.py# Internal LLM ↔ Pydantic bridging schemas
│   ├── validators.py        # Cross-field validation rules
│   └── ner.py               # LegalNER (spaCy / Blackstone) [optional]
│
├── utils/
│   ├── provenance.py        # ProvenanceTracker · ChunkRecord  ← NEW
│   ├── routing.py           # ConfidenceRouter · ReviewItem · RoutingResult  ← NEW
│   ├── audit.py             # AuditLogger · JSONL/Postgres/Null backends  ← NEW
│   ├── confidence.py        # Overall confidence scoring helpers
│   ├── normalizers.py       # Date · currency · entity normalisation
│   ├── comparators.py       # ContractComparator
│   └── exporters.py         # JSON · CSV · Excel
│
├── eval/                    # ← NEW package
│   ├── cases.py             # EvalCase · EvalSuite (YAML/JSON loader)
│   ├── metrics.py           # FieldResult · CaseResult · ExtractionMetrics
│   └── harness.py           # EvalHarness (extractor-agnostic runner)
│
├── storage/
│   ├── models.py            # Storage-layer Document · Clause · ProcessingLog
│   ├── repository.py        # DocumentRepository · ClauseRepository
│   ├── connection.py        # psycopg2 connection management
│   ├── config.py            # DB config from environment
│   └── schema.sql           # DDL for documents · clauses · processing_log
│
├── taxonomy/
│   ├── cuad.py              # CUAD 41-type taxonomy
│   └── schemas.py           # Taxonomy validation schemas
│
├── prompts/
│   ├── clause_extraction.py
│   ├── financial_extraction.py
│   ├── party_extraction.py
│   └── risk_analysis.py
│
└── exceptions.py            # Typed exception hierarchy
```

---

## Installation

```bash
git clone https://github.com/aahepburn/Contract-Clause-Extractor.git
cd Contract-Clause-Extractor

# Full install (all optional extras)
pip install -e ".[all]"

# Or pick what you need
pip install -e ".[storage]"   # PostgreSQL persistence
pip install -e ".[network]"   # URLLoader / APILoader (requests)
pip install -e ".[eval]"      # EvalHarness (pyyaml)
pip install -e ".[ocr]"       # OCR support for scanned PDFs
pip install -e ".[spacy]"     # Named entity recognition
pip install -e ".[local]"     # Local LLM via Ollama
pip install -e ".[retrieval]" # pgvector + sentence-transformers
```

Configure API keys:

```bash
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=...
```

---

## Quick start

```python
from contractex import extract_contract

contract = extract_contract("contract.pdf")
print(f"Parties: {[p.name for p in contract.parties]}")
print(f"Clauses: {len(contract.clauses)}")
print(f"Risks:   {len(contract.critical_risks)} critical")
contract.to_excel("output.xlsx")
```

---

## Contract extraction pipeline

The `ContractExtractor` runs a three-phase LLM pipeline over any document.

```mermaid
sequenceDiagram
    participant C as Caller
    participant CE as ContractExtractor
    participant L as DocumentLoader
    participant CH as Chunker
    participant LLM as LLMProvider
    participant RA as RiskAnalyzer

    C->>CE: extract("contract.pdf")
    CE->>L: load(path)
    L-->>CE: text (str)
    CE->>CH: chunk(text)
    CH-->>CE: chunks[]

    Note over CE,LLM: Phase 1 — contract metadata + parties
    CE->>LLM: extract_structured(preamble, ContractInfoSchema)
    LLM-->>CE: parties, dates, governing_law

    Note over CE,LLM: Phase 2 — per-chunk clause + financial extraction
    loop each chunk (parallel)
        CE->>LLM: extract_structured(chunk, ClausesSchema)
        LLM-->>CE: clauses[]
        CE->>LLM: extract_structured(chunk, FinancialSchema)
        LLM-->>CE: financial_terms[]
    end

    Note over CE: Phase 3 — deduplicate + build models
    CE->>RA: analyze(contract)
    RA-->>CE: risks[]
    CE-->>C: Contract
```

### Custom configuration

```python
from contractex import ContractExtractor
from contractex.llm import AnthropicProvider
from contractex.loaders import PDFLoader
from contractex.chunking import ClauseAwareChunker

extractor = ContractExtractor(
    llm_provider=AnthropicProvider(model="claude-opus-4-6"),
    document_loader=PDFLoader(ocr_enabled=True),
    chunking_strategy=ClauseAwareChunker(max_chunk_size=4000, overlap=200),
    confidence_threshold=0.80,
)

contract = extractor.extract(
    "complex_contract.pdf",
    analyze_risks=True,
    extract_financial=True,
)
```

### Batch processing

```python
contracts = extractor.extract_batch(
    ["msa.pdf", "nda.pdf", "sow.pdf"],
    max_workers=4,
)

# Async variant
import asyncio
contract = asyncio.run(extractor.extract_async("contract.pdf"))
```

### Cost estimation (before extraction)

```python
estimate = extractor.estimate_extraction_cost("long_contract.pdf")
print(f"Estimated cost: ${estimate['estimated_cost']:.4f}")
print(f"Chunks: {estimate['num_chunks']}")
```

---

## General legal document pipeline

`LegalDocument` generalises beyond contracts to any legal document: statutes, regulations, case opinions, identity documents, government forms.

```mermaid
graph LR
    subgraph Input
        S[Source<br/>URL / API / File]
    end
    subgraph Load["Load + Chunk"]
        SA[SourceAdapter<br/>URLLoader / APILoader]
        CH[Chunker]
    end
    subgraph Extract["LLM Extract"]
        LLM[LLMProvider<br/>extract_structured]
        LD[LegalDocument<br/>extracted_fields<br/>field_confidences]
    end
    subgraph Annotate
        PT[ProvenanceTracker<br/>annotate_all]
    end
    subgraph Route
        CR[ConfidenceRouter<br/>route_document]
        ACC[accepted dict]
        REV[review_queue]
        REJ[rejected list]
    end
    subgraph Audit
        AL[AuditLogger<br/>log_extraction]
    end

    S --> SA --> CH --> LLM --> LD --> PT --> CR
    CR --> ACC
    CR --> REV
    CR --> REJ
    LD --> AL
    CR --> AL
```

### Example — statute extraction

```python
from contractex.loaders import URLLoader
from contractex.core.legal_document import LegalDocument, DocType, LegalDocumentMetadata
from contractex.utils.provenance import ProvenanceTracker
from contractex.utils.routing import ConfidenceRouter
from contractex.utils.audit import AuditLogger
from contractex.chunking import ClauseAwareChunker
from contractex.llm import OpenAIProvider

url = "https://www.law.cornell.edu/uscode/text/17/107"

# 1. Fetch
loader = URLLoader()
fetch = loader.fetch(url)

# 2. Chunk + register provenance
chunker = ClauseAwareChunker()
chunks = chunker.chunk(fetch.content)

tracker = ProvenanceTracker(source_url=url)
tracker.register_chunks(chunks)

# 3. LLM extraction
llm = OpenAIProvider(model="gpt-4o")
# ... call llm.extract_structured(prompt, YourSchema) ...

# 4. Build LegalDocument
doc = LegalDocument(
    doc_type=DocType.STATUTE,
    jurisdiction="US-Federal",
    citation="17 U.S.C. § 107",
    metadata=LegalDocumentMetadata(
        source_url=url,
        content_hash=fetch.content_hash,
    ),
)
doc.set_field("title", "Fair Use", confidence=0.99)
doc.set_field("effective_date", "1976-10-19", confidence=0.95)

# 5. Annotate provenance
tracker.annotate_all(doc)
print(f"Provenance coverage: {doc.provenance_coverage:.0%}")

# 6. Route + audit
router = ConfidenceRouter(accept_threshold=0.85)
result = router.route_document(doc)

with AuditLogger.from_jsonl("audit/pipeline.jsonl") as audit:
    audit.log_extraction(
        doc.doc_id or "statute-107",
        fields_extracted=list(result.accepted),
        fields_rejected=result.rejected_field_names,
        overall_confidence=sum(doc.field_confidences.values()) / len(doc.field_confidences),
    )
    if result.needs_review:
        audit.log_review_request(
            doc.doc_id or "statute-107",
            fields=result.review_field_names,
        )
```

---

## Network loaders

`SourceAdapter` extends `DocumentLoader` with HTTP fetching, ETag-based change detection, and exponential-backoff retry.

```mermaid
classDiagram
    class DocumentLoader {
        <<abstract>>
        +load(source) str
        +load_with_metadata(source) dict
        +supports(file_path) bool
    }
    class SourceAdapter {
        <<abstract>>
        +fetch(source, cache) FetchResult
        +changed_since(source, cache) bool
        #_retry(fn) Any
        #_hash(content) str
    }
    class URLLoader {
        +strip_html: bool
        +extra_headers: dict
        +fetch(source, cache) FetchResult
        -_strip_html(html) str
        -_load_pdf_bytes(data) str
    }
    class APILoader {
        +text_field: str
        +auth_header: str
        +paginate: bool
        +max_pages: int
        +fetch(source, cache) FetchResult
        -_extract_text(data) str
        -_next_link(response, data) str
    }
    DocumentLoader <|-- SourceAdapter
    SourceAdapter <|-- URLLoader
    SourceAdapter <|-- APILoader
```

### URLLoader

```python
from contractex.loaders import URLLoader, FetchCache

loader = URLLoader(
    timeout=30,
    max_retries=3,
    strip_html=True,
    headers={"Accept-Language": "en-US"},
)

# First fetch — captures ETag for next time
result = loader.fetch("https://ecfr.gov/current/title-17/section-107")
cache = result.to_cache()

# Next day — conditional GET; returns changed=False if nothing changed
if loader.changed_since("https://ecfr.gov/current/title-17/section-107", cache):
    result = loader.fetch("https://ecfr.gov/current/title-17/section-107")
    # process new content ...
```

### APILoader

```python
from contractex.loaders import APILoader

# CourtListener REST API example
loader = APILoader(
    text_field="plain_text",
    auth_header="Token your-api-key",
    params={"jurisdiction": "scotus"},
    paginate=True,
    max_pages=5,
)

result = loader.fetch("https://www.courtlistener.com/api/rest/v3/opinions/")
print(result.content[:500])
```

---

## Provenance tracking

`ProvenanceTracker` maps every extracted field back to the exact chunk — and character offsets within it — that it came from.

```mermaid
graph LR
    subgraph Register
        C0["chunk-0000-ab12<br/>Section 1: The parties agree…"]
        C1["chunk-0001-cd34<br/>Section 2: Termination…"]
        C2["chunk-0002-ef56<br/>Section 3: Governing law…"]
    end

    subgraph Resolve
        Q1["query: '30 days notice'"]
        Q2["query: 'state of Delaware'"]
    end

    subgraph Spans
        S1["SourceSpan<br/>chunk_id: chunk-0001-cd34<br/>page: 2 · char: 445–458"]
        S2["SourceSpan<br/>chunk_id: chunk-0002-ef56<br/>page: 3 · char: 892–909"]
    end

    Q1 -->|exact match| S1
    Q2 -->|exact match| S2
    C1 -. contains .-> S1
    C2 -. contains .-> S2
```

```python
from contractex.utils.provenance import ProvenanceTracker

tracker = ProvenanceTracker(source_url="https://example.com/doc.pdf")
tracker.register_chunks(chunks, page_map={0: 1, 1: 2, 2: 3})

# After LLM extraction places a value in doc.extracted_fields:
tracker.annotate_all(doc)

# Inspect coverage
stats = tracker.coverage(doc)
print(f"Provenance coverage: {stats['coverage_ratio']:.0%}")

# Resolve a single value manually
span = tracker.find_span("thirty days notice")
if span:
    print(f"Found at page {span.page}, chars {span.char_start}–{span.char_end}")
```

---

## Confidence routing

`ConfidenceRouter` partitions extracted fields into three queues based on per-field confidence scores. Per-field threshold overrides support stricter rules for high-stakes fields.

```mermaid
graph TD
    F[Extracted Field<br/>name=GARCIA<br/>confidence=0.60]

    F --> D{Confidence check}
    D -->|≥ accept_threshold 0.80| ACC["AUTO_ACCEPT<br/>→ result.accepted"]
    D -->|reject_t ≤ conf < accept_t| REV["HUMAN_REVIEW<br/>→ result.review_queue<br/>sorted by confidence ↑"]
    D -->|< reject_threshold 0.40| REJ["AUTO_REJECT<br/>→ result.rejected"]
```

```python
from contractex.utils.routing import ConfidenceRouter

router = ConfidenceRouter(
    accept_threshold=0.80,
    reject_threshold=0.40,
    # Tighter rules for high-stakes fields
    field_thresholds={
        "passport_number": (0.95, 0.70),
        "date_of_birth":   (0.90, 0.60),
    },
)

result = router.route_document(doc)

print(f"Accepted: {list(result.accepted)}")
print(f"Review:   {result.review_field_names}")  # sorted least-confident first
print(f"Rejected: {result.rejected_field_names}")
print(result.summary())
# → RoutingResult(accepted=4, review=2, rejected=1, acceptance_rate=57%)

# Route a plain dict (pre-LegalDocument pipelines)
result = router.route_dict(
    fields={"name": "SMITH", "dob": "1990-01-15"},
    confidences={"name": 0.95, "dob": 0.55},
)
```

---

## Audit logging

`AuditLogger` records every material pipeline operation to an append-only, structured log — satisfying GDPR Article 30 record-of-processing requirements.

```mermaid
graph LR
    subgraph Events
        E1[log_ingestion]
        E2[log_extraction]
        E3[log_review_request]
        E4[log_review_completion]
        E5[log_deletion]
        E6[log_error]
    end

    subgraph AuditLogger
        AL[AuditLogger facade]
    end

    subgraph Backends
        NB[NullAuditBackend<br/>testing / disabled]
        JB[JSONLAuditBackend<br/>append-only .jsonl file<br/>thread-safe]
        PB[PostgresAuditBackend<br/>audit_log table<br/>autocommit · auto-DDL]
    end

    E1 & E2 & E3 & E4 & E5 & E6 --> AL
    AL --> NB
    AL --> JB
    AL --> PB
```

```python
from contractex.utils.audit import AuditLogger

# File-backed (single machine)
with AuditLogger.from_jsonl("audit/pipeline.jsonl") as audit:
    audit.log_ingestion("doc-123", source_url="https://ecfr.gov/...")
    # ... run pipeline ...
    audit.log_extraction(
        "doc-123",
        fields_extracted=["title", "effective_date"],
        fields_rejected=["amendment_date"],
        overall_confidence=0.91,
    )
    if needs_human_review:
        audit.log_review_request("doc-123", fields=["amendment_date"])

# GDPR deletion
audit.log_deletion("doc-123", user_id="gdpr-request-456")

# Postgres-backed (multi-worker)
audit = AuditLogger.from_postgres("postgresql://user:pw@host/db")
```

**Events are never lost on backend failure** — write errors are captured and re-emitted via the standard `logging` module, never raised to the caller.

---

## Eval harness

`EvalHarness` runs labeled test suites against any extraction callable and produces quality metrics with pytest-compatible assertion helpers.

```mermaid
graph TD
    subgraph Suite["EvalSuite  (YAML / JSON)"]
        C1["EvalCase: us_statute_fair_use<br/>expected: jurisdiction=US-Federal<br/>           citation=17 U.S.C. § 107"]
        C2["EvalCase: spanish_passport_garcia<br/>expected: surname=GARCIA<br/>           mrz_valid=true<br/>field_weights: mrz_valid=3.0"]
    end

    subgraph Harness
        EH[EvalHarness<br/>extractor_fn]
    end

    subgraph Results
        CR1[CaseResult: us_statute<br/>PASS · 2/2 fields]
        CR2[CaseResult: spanish_passport<br/>PARTIAL · 1/2 fields]
        EM[ExtractionMetrics<br/>field_accuracy=75%<br/>case_accuracy=50%]
    end

    C1 & C2 --> EH --> CR1 & CR2 --> EM
```

### Suite file (YAML)

```yaml
# tests/eval/immigration_cases.yaml
- id: spanish_passport_garcia
  description: "Sample Spanish passport"
  doc_type: identity_doc
  input_path: tests/fixtures/passport_sample.pdf
  expected_fields:
    surname: GARCIA
    given_name: JOSE
    nationality: ESP
    mrz_valid: true
  field_weights:
    mrz_valid: 3.0   # MRZ validity is load-bearing — weight it higher
  tags: [passport, spanish, immigration]

- id: us_statute_fair_use
  doc_type: statute
  input_text: "Notwithstanding the provisions of sections 106 and 106A ..."
  expected_fields:
    jurisdiction: US-Federal
    citation: "17 U.S.C. § 107"
  tags: [statute, copyright]
```

### Running the harness

```python
from contractex.eval import EvalHarness, EvalSuite

suite = EvalSuite.load("tests/eval/immigration_cases.yaml")

# Wire in your extraction pipeline
def my_extractor(case):
    doc = pipeline.process(case.input_path or case.input_text)
    return doc.extracted_fields

harness = EvalHarness(extractor_fn=my_extractor)
metrics = harness.run(suite)

print(metrics.report())
# ══════════════════════════════════════════════════════════════
#   ContractEx Eval Report
# ══════════════════════════════════════════════════════════════
#   Suite size:     2 cases
#   Passed:         1 (50.0% case accuracy)
#   Errors:         0
#   Field accuracy: 75.0% (weighted)
#   ...

# CI gate (raises AssertionError with full report on failure)
metrics.assert_min_field_accuracy(0.90)
```

---

## Storage layer

The storage layer persists documents, extracted clauses, and processing logs in PostgreSQL.

```mermaid
erDiagram
    documents {
        serial id PK
        varchar filename UK
        varchar file_hash
        bytea file_data
        text extracted_text
        jsonb metadata
        timestamp uploaded_at
        timestamp updated_at
    }
    clauses {
        serial id PK
        integer document_id FK
        text clause_text
        varchar clause_type
        integer page_number
        float bbox_x
        float bbox_y
        float bbox_width
        float bbox_height
        float confidence_score
        integer parent_clause_id FK
        jsonb metadata
        timestamp created_at
    }
    processing_log {
        serial id PK
        integer document_id FK
        varchar processing_stage
        varchar status
        text error_message
        timestamp created_at
    }

    documents ||--o{ clauses : "has"
    documents ||--o{ processing_log : "tracked by"
    clauses ||--o{ clauses : "parent_clause_id"
```

```python
from contractex.storage import DocumentRepository, ClauseRepository, Document

doc = Document(
    filename="contract.pdf",
    file_hash=Document.compute_hash(pdf_bytes),
    file_data=pdf_bytes,
    extracted_text=text,
    metadata={"contract_type": "NDA"},
)
repo = DocumentRepository()
doc_id = repo.insert(doc)
```

Enable vector search by running the embeddings migration:

```bash
psql clause_docs < contractex/storage/migrations/add_embeddings.sql
```

See [CLAUSE_RETRIEVAL_GUIDE.md](CLAUSE_RETRIEVAL_GUIDE.md) for the full hybrid search implementation guide.

---

## LLM providers

All providers implement the same `LLMProvider` ABC so they are interchangeable.

```mermaid
classDiagram
    class LLMProvider {
        <<abstract>>
        +extract_structured(prompt, schema) BaseModel
        +complete(prompt) str
        +estimate_cost(text) float
        +count_tokens(text) int
        +context_window int
        +model str
    }
    class OpenAIProvider { model: gpt-4o }
    class AnthropicProvider { model: claude-opus-4-6 }
    class GoogleProvider { model: gemini-2.5-pro }
    class LocalProvider { model: llama3.1 via Ollama }

    LLMProvider <|-- OpenAIProvider
    LLMProvider <|-- AnthropicProvider
    LLMProvider <|-- GoogleProvider
    LLMProvider <|-- LocalProvider
```

| Provider | Recommended model | Cost/contract | Best for |
| --- | --- | --- | --- |
| OpenAI | `gpt-4o` | ~$0.025 | Highest accuracy |
| Anthropic | `claude-opus-4-6` | ~$0.030 | Long documents |
| Google | `gemini-2.5-pro` | ~$0.002 | Speed + cost |
| Local | any Ollama model | $0 | Privacy / offline |

```python
from contractex.llm import OpenAIProvider, AnthropicProvider, GoogleProvider, LocalProvider

llm = OpenAIProvider(model="gpt-4o", temperature=0.0)
llm = AnthropicProvider(model="claude-opus-4-6")
llm = GoogleProvider(model="gemini-2.5-pro")
llm = LocalProvider(model="llama3.1:8b")  # requires Ollama running locally
```

---

## Examples

| File | What it shows |
| --- | --- |
| [examples/basic_extraction.py](examples/basic_extraction.py) | One-line contract extraction |
| [examples/advanced_extraction.py](examples/advanced_extraction.py) | Custom LLM + chunker config |
| [examples/batch_processing.py](examples/batch_processing.py) | Parallel extraction over many documents |
| [examples/fastapi_service.py](examples/fastapi_service.py) | REST API wrapper |
| [examples/storage_example.py](examples/storage_example.py) | PostgreSQL persistence |
| [examples/ner_example.py](examples/ner_example.py) | Named entity recognition |
| [examples/local_llm_example.py](examples/local_llm_example.py) | Offline extraction with Ollama |
| [examples/langchain_integration.py](examples/langchain_integration.py) | LangChain compatibility |
| [examples/dataset_loading.py](examples/dataset_loading.py) | CUAD / ACORD / LePaRD datasets |

---

## Development

```bash
# Run all unit tests (no database required)
python -m pytest tests/ -m "not integration" --no-cov -v

# Run with coverage
python -m pytest --cov=contractex --cov-report=html

# Code quality
black contractex/
ruff check contractex/ --fix
mypy contractex/
```

Optional extras for development:

```bash
pip install -e ".[dev]"       # pytest, black, ruff, mypy, coverage
pip install -e ".[eval]"      # pyyaml for YAML eval suites
pip install -e ".[network]"   # requests for URLLoader / APILoader
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
