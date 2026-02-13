# ContractEx: Modern Contract Intelligence for Python

 **LLM-powered contract analysis** |  **CUAD taxonomy** |  **Risk detection** | **Privacy-first**

ContractEx is a production-ready Python library for intelligent contract analysis using large language models. Extract clauses, identify parties, analyze risks, and extract financial terms from legal documents with a clean, intuitive API.

[![PyPI version](https://badge.fury.io/py/contractex.svg)](https://badge.fury.io/py/contractex)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

---

##  Features

- ** Simple API**: Extract contracts with a single line of code
- ** Multi-LLM Support**: OpenAI (GPT-4o), Anthropic (Claude), Google (Gemini), local models (Llama via Ollama)
- ** CUAD Taxonomy**: 41 standard clause types from the Contract Understanding Atticus Dataset
- ** Risk Analysis**: Automatic detection of unfavorable terms and potential risks
- ** Financial Extraction**: Extract payment terms, amounts, and conditions
- ** Privacy-First**: Local LLM support for sensitive documents
- ** Named Entity Recognition**: Extract parties, dates, and legal entities using spaCy/Blackstone
- ** Dataset Loaders**: Built-in access to ACORD, CUAD, and LePaRD benchmarks
- ** Extensible**: LangChain and spaCy compatibility
- ** Export**: JSON, Excel, CSV output formats
- ** Fast**: Batch processing with parallel execution
- ** Type-Safe**: Full type hints and Pydantic models

---

##  Installation

### Quick Install

```bash
# Clone repository
git clone https://github.com/aahepburn/Contract-Clause-Extractor.git
cd Contract-Clause-Extractor

# Install all dependencies (single requirements file)
pip install -r requirements.txt

# Or install as editable package
pip install -e .
```

### Using pyproject.toml (Optional Feature Groups)

```bash
# Install specific feature groups
pip install -e ".[ocr]"        # OCR support for scanned PDFs
pip install -e ".[spacy]"      # Named Entity Recognition
pip install -e ".[langchain]"  # LangChain integration
pip install -e ".[local]"      # Local LLM support (Ollama)
pip install -e ".[storage]"    # PostgreSQL storage
pip install -e ".[datasets]"   # Dataset loaders (ACORD, CUAD, LePaRD)
pip install -e ".[all]"        # All features
```

### Configuration

```bash
# Create .env file with your API keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
GOOGLE_API_KEY=your-google-api-key
```

---

## Quick Start

### Basic Usage (< 10 lines)

```python
from contractex import extract_contract

# Extract contract with one line
contract = extract_contract("contract.pdf")

# Access results
print(f"Parties: {', '.join([p.name for p in contract.parties])}")
print(f"Clauses: {len(contract.clauses)}")
print(f"Risks: {len(contract.risks)} ({len(contract.critical_risks)} critical)")

# Export
contract.to_json("output.json")
contract.to_excel("output.xlsx")
```

### Advanced Usage

```python
from contractex import ContractExtractor
from contractex.llm import OpenAIProvider
from contractex.loaders import PDFLoader
from contractex.chunking import ClauseAwareChunker

# Configure custom components
llm = OpenAIProvider(model="gpt-4o", temperature=0.0)
loader = PDFLoader(ocr_enabled=True, preserve_layout=True)
chunker = ClauseAwareChunker(max_chunk_size=4000, overlap=200)

# Create extractor
extractor = ContractExtractor(
    llm_provider=llm,
    document_loader=loader,
    chunking_strategy=chunker,
    confidence_threshold=0.8
)

# Extract with options
contract = extractor.extract(
    "complex_contract.pdf",
    analyze_risks=True,
    extract_financial=True
)
```

---

## Dataset Loading

Load popular legal contract datasets for training and evaluation:

```python
from contractex.data import load_cuad, load_acord, load_lepard

# Load CUAD (Contract Understanding Atticus Dataset)
cuad_df = load_cuad(split='train')
print(f"Loaded {len(cuad_df)} contracts with 41 clause types")

# Load ACORD (clause retrieval benchmark)
acord_df = load_acord(split='train')

# Load LePaRD (legal passage retrieval)
lepard_df = load_lepard()
```

See [contractex/data/README.md](contractex/data/README.md) for full documentation.

---

## Use Cases

### Legal Teams
- Contract Review & Due Diligence
- Risk Assessment & Compliance
- M&A Document Analysis

### Procurement Teams
- Vendor Agreement Review
- Payment Terms Verification
- SLA Analysis

### Sales & Business Development
- Deal Analysis & Redlining Support
- Contract Comparison
- Archive Search

---

## LLM Providers

- **OpenAI (GPT-4o)**: Best accuracy (~$0.025/contract)
- **Anthropic (Claude)**: Large documents (~$0.030/contract)
- **Google (Gemini)**: Fast and cost-effective (~$0.002/contract)
- **Local (Llama)**: Privacy-first, zero cost

---

## Documentation & Examples

- **[CHANGELOG.md](CHANGELOG.md)** - Version history and release notes
- **[Examples Directory](examples/)** - Ready-to-run examples:
  - `basic_extraction.py` - Simple usage
  - `advanced_extraction.py` - Custom configuration
  - `batch_processing.py` - Multiple contracts
  - `langchain_integration.py` - LangChain usage
  - `local_llm_example.py` - Privacy-first local
  - `fastapi_service.py` - REST API
  - `dataset_loading.py` - Working with legal datasets
  - `ner_example.py` - Named entity recognition
  - `storage_example.py` - PostgreSQL persistence

Run examples: `python examples/basic_extraction.py`

---

## Testing & Development

```bash
# Run all tests
pytest

# With coverage
pytest --cov=contractex --cov-report=html

# Code quality
black contractex/           # Format code
ruff check contractex/ --fix  # Lint
mypy contractex/             # Type check
```

---

## Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## License

Apache 2.0 License - see [LICENSE](LICENSE) for details.

---

