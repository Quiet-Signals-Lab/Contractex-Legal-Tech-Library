# ContractEx - Quick Reference

## 🚀 Installation

```bash
# Clone and install
git clone https://github.com/aahepburn/Contract-Clause-Extractor.git
cd Contract-Clause-Extractor
./install.sh  # Interactive installer

# Or manual
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## ⚙️ Configuration

```bash
# Create .env file
cp .env.example .env

# Add your API keys
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."
```

## 📖 Basic Usage

### Simple (One-line)
```python
from contractex import extract_contract

# Extract from any document
contract = extract_contract("contract.pdf")

# Access data
print(f"Title: {contract.title}")
print(f"Parties: {[p.name for p in contract.parties]}")
print(f"Clauses: {len(contract.clauses)}")

# Export
contract.to_excel("output.xlsx")
```

### Advanced (Customized)
```python
from contractex import ContractExtractor
from contractex.llm import OpenAIProvider, AnthropicProvider
from contractex.loaders import PDFLoader
from contractex.chunking import ClauseAwareChunker

# Configure components
llm = OpenAIProvider(model="gpt-4o", temperature=0.1)
loader = PDFLoader(ocr_enabled=True)
chunker = ClauseAwareChunker(max_chunk_size=2000)

# Create extractor
extractor = ContractExtractor(
    llm_provider=llm,
    document_loader=loader,
    chunking_strategy=chunker,
    confidence_threshold=0.8
)

# Extract
contract = extractor.extract("contract.pdf")

# Filter high-confidence results
good_clauses = contract.high_confidence_clauses
critical_risks = contract.critical_risks
```

## 🔍 Key Operations

### Extract Parties
```python
contract = extract_contract("contract.pdf")
for party in contract.parties:
    print(f"{party.name} ({party.role})")
```

### Find Specific Clause Types
```python
from contractex.taxonomy import CUADClauseType

# Get all termination clauses
term_clauses = [
    c for c in contract.clauses 
    if c.cuad_type == CUADClauseType.TERMINATION_FOR_CONVENIENCE
]
```

### Analyze Risks
```python
from contractex.core.analyzers import RiskAnalyzer

analyzer = RiskAnalyzer(llm_provider=llm)
risks = analyzer.analyze(contract)

for risk in risks:
    if risk.severity == "critical":
        print(f"⚠️  {risk.description}")
        print(f"   Recommendation: {risk.recommendation}")
```

### Compare Contracts
```python
contract1 = extract_contract("v1.pdf")
contract2 = extract_contract("v2.pdf")

comparison = contract1.compare_with(contract2)
print(f"Similarity: {comparison.similarity_score:.2%}")
print(f"Added: {len(comparison.added_clauses)}")
print(f"Removed: {len(comparison.removed_clauses)}")
print(f"Modified: {len(comparison.modified_clauses)}")
```

### Batch Processing
```python
import glob
from concurrent.futures import ThreadPoolExecutor

files = glob.glob("contracts/*.pdf")

with ThreadPoolExecutor(max_workers=5) as executor:
    contracts = list(executor.map(extract_contract, files))

# Export all
from contractex.utils.exporters import export_batch_to_excel
export_batch_to_excel(contracts, "all_contracts.xlsx")
```

## 🤖 LLM Providers

### OpenAI
```python
from contractex.llm import OpenAIProvider

llm = OpenAIProvider(
    model="gpt-4o",          # or "gpt-4o-mini" 
    api_key="sk-...",        # or from env
    temperature=0.1,
    max_tokens=4000
)
```

### Anthropic (Claude)
```python
from contractex.llm import AnthropicProvider

llm = AnthropicProvider(
    model="claude-3-5-sonnet-20241022",
    api_key="sk-ant-...",
    temperature=0.1
)
```

### Local (Ollama)
```python
from contractex.llm import LocalProvider

llm = LocalProvider(
    model="llama3.1:8b",
    base_url="http://localhost:11434"
)
```

### LangChain
```python
from langchain_openai import ChatOpenAI
from contractex.llm import LangChainProvider

langchain_llm = ChatOpenAI(model="gpt-4o")
llm = LangChainProvider(langchain_llm)
```

## 📄 Document Loaders

### PDF with OCR
```python
from contractex.loaders import PDFLoader

loader = PDFLoader(
    ocr_enabled=True,
    ocr_lang="eng"
)
text = loader.load("scanned.pdf")
```

### DOCX
```python
from contractex.loaders import DOCXLoader

loader = DOCXLoader(extract_headers=True)
text = loader.load("contract.docx")
```

### Auto-detect
```python
from contractex.loaders import AutoLoader

loader = AutoLoader()
text = loader.load("contract.pdf")  # Automatically detects type
```

## 📊 Export Formats

### JSON
```python
# Pretty printed JSON
json_str = contract.to_json()
with open("output.json", "w") as f:
    f.write(json_str)
```

### Excel (Recommended)
```python
# Multiple sheets: summary, parties, clauses, financial, risks
contract.to_excel("contract_analysis.xlsx")
```

### CSV
```python
# Export clauses to CSV
df = contract.to_dataframe()
df.to_csv("clauses.csv", index=False)
```

### pandas DataFrame
```python
# For further analysis
import pandas as pd

df = contract.to_dataframe()
print(df.groupby('cuad_type')['confidence'].mean())
```

## 🧪 Testing

```bash
# Run all tests
pytest

# Unit tests only
pytest -m unit

# With coverage
pytest --cov=contractex --cov-report=html

# Specific test file
pytest tests/test_models.py -v
```

## 🛠️ Development

```bash
# Format code
black contractex/ tests/ examples/

# Lint
ruff check contractex/ --fix

# Type check
mypy contractex/

# All checks
black contractex/ && ruff check contractex/ && mypy contractex/ && pytest
```

## 📝 Common Patterns

### Custom Risk Playbook
```python
from contractex.core.analyzers import RiskAnalyzer

playbook = {
    "payment_terms": {
        "patterns": ["net 90", "120 days"],
        "severity": "high",
        "message": "Extended payment terms"
    }
}

analyzer = RiskAnalyzer(playbook=playbook)
risks = analyzer.analyze(contract)
```

### Confidence Filtering
```python
# Only use high-confidence extractions
HIGH_CONFIDENCE = 0.85

reliable_clauses = [
    c for c in contract.clauses 
    if c.confidence >= HIGH_CONFIDENCE
]
```

### Template Matching
```python
from contractex.utils.comparators import ContractComparator

template = extract_contract("template.pdf")
comparator = ContractComparator()

# Check if contract follows template
for contract_file in ["contract1.pdf", "contract2.pdf"]:
    contract = extract_contract(contract_file)
    similarity = comparator.compare(template, contract)
    
    if similarity.similarity_score < 0.7:
        print(f"⚠️  {contract_file} deviates from template")
        print(f"Missing clauses: {similarity.missing_clauses}")
```

## 🔧 API Quick Reference

### Core Classes
- `ContractExtractor` - Main extraction orchestrator
- `Contract` - Extracted contract data model
- `Party` - Legal entity (company, person)
- `Clause` - Contract clause with type and confidence
- `FinancialTerm` - Payment terms, amounts
- `RiskFlag` - Identified risk with severity

### LLM Providers
- `LLMProvider` - Abstract base class
- `OpenAIProvider` - OpenAI GPT models
- `AnthropicProvider` - Anthropic Claude models
- `LocalProvider` - Local models via Ollama
- `LangChainProvider` - LangChain integration

### Loaders
- `DocumentLoader` - Abstract base class
- `PDFLoader` - PDF with optional OCR
- `DOCXLoader` - Word documents
- `AutoLoader` - Auto-detecting loader

### Utilities
- `CUADClassifier` - Classify clauses by CUAD taxonomy
- `RiskAnalyzer` - Detect and analyze risks
- `ContractComparator` - Compare contracts
- `DateNormalizer` / `CurrencyNormalizer` - Data normalization

## 📚 Examples

All examples in `examples/` directory:
1. `basic_extraction.py` - Simple usage
2. `advanced_extraction.py` - Custom configuration
3. `batch_processing.py` - Multiple contracts
4. `langchain_integration.py` - LangChain usage
5. `local_llm_example.py` - Privacy-first local
6. `fastapi_service.py` - REST API
7. `risk_analysis_demo.py` - Risk detection

Run any example:
```bash
python examples/basic_extraction.py
```

## 🐛 Troubleshooting

### Import Error
```bash
# Reinstall in editable mode
pip install -e .
```

### API Key Not Found
```bash
# Check .env file exists
ls -la .env

# Or set environment variable
export OPENAI_API_KEY="sk-..."
```

### OCR Not Working
```bash
# Install Tesseract
brew install tesseract  # macOS
sudo apt install tesseract-ocr  # Linux
```

### Out of Memory
```python
# Use smaller chunks
chunker = ClauseAwareChunker(max_chunk_size=1000)
```

## 📖 Documentation Files

- [README.md](README.md) - Main documentation
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [NEXT_STEPS.md](NEXT_STEPS.md) - Development roadmap
- [CONTRIBUTING.md](CONTRIBUTING.md) - Contribution guidelines
- [CHANGELOG.md](CHANGELOG.md) - Version history
- [RESTRUCTURING_SUMMARY.md](RESTRUCTURING_SUMMARY.md) - What was built

## 🆘 Getting Help

1. Check documentation files above
2. Look at examples in `examples/`
3. Read error messages carefully
4. Search issues on GitHub
5. Open new issue with details

## 🎯 Next Steps

See [NEXT_STEPS.md](NEXT_STEPS.md) for detailed roadmap and priorities.

---

**Version:** 0.1.0  
**Status:** Production-ready structure, implementation in progress  
**License:** MIT
