# ContractEx: Modern Contract Intelligence for Python

🔥 **LLM-powered contract analysis** | 📋 **CUAD taxonomy** | 🛡️ **Risk detection** | 🔒 **Privacy-first**

ContractEx is a production-ready Python library for intelligent contract analysis using large language models. Extract clauses, identify parties, analyze risks, and extract financial terms from legal documents with a clean, intuitive API.

[![PyPI version](https://badge.fury.io/py/contractex.svg)](https://badge.fury.io/py/contractex)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## ✨ Features

- **🚀 Simple API**: Extract contracts with a single line of code
- **🧠 Multi-LLM Support**: OpenAI (GPT-4o), Anthropic (Claude), local models (Llama via Ollama)
- **📋 CUAD Taxonomy**: 41 standard clause types from the Contract Understanding Atticus Dataset
- **🛡️ Risk Analysis**: Automatic detection of unfavorable terms and potential risks
- **💰 Financial Extraction**: Extract payment terms, amounts, and conditions
- **🔒 Privacy-First**: Local LLM support for sensitive documents
- **🔗 Extensible**: LangChain and spaCy compatibility
- **📊 Export**: JSON, Excel, CSV output formats
- **⚡ Fast**: Batch processing with parallel execution
- **✅ Type-Safe**: Full type hints and Pydantic models

---

## 📦 Installation

```bash
# Basic installation
pip install contractex

# With optional dependencies
pip install contractex[all]  # All features

# Or install specific features
pip install contractex[ocr]        # OCR support for scanned PDFs
pip install contractex[langchain]  # LangChain integration
pip install contractex[local]      # Local LLM support (Ollama)
```

---

## 🚀 Quick Start

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

## 🎯 Use Cases

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

## 🧠 LLM Providers

- **OpenAI (GPT-4o)**: Best accuracy (~$0.025/contract)
- **Anthropic (Claude)**: Large documents (~$0.030/contract)
- **Local (Llama)**: Privacy-first, zero cost

---

## 📚 Documentation

- [Quick Start Guide](QUICKSTART.md)
- [API Reference](docs/api_reference.md)
- [Examples](examples/)

---

## 🤝 Contributing

Contributions welcome! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## 📄 License

MIT License - see [LICENSE](LICENSE) for details.

---

**Built with ❤️ for the legal tech community**
| **Llama-3.2-90B** | 90B | 72-76% | ❌ | 8 languages | Meta | Ollama (local) ✅ |
| **Llama-3.2-11B-Vision** | 11B | N/A | ✅ | 8 languages | Meta | Ollama ✅ |
| **EuroVLM-9B** | 9B | 70-75% | ✅ | 35 EU languages | OpenRAIL | HuggingFace ✅ |
| **Qwen2.5-VL-32B** | 32B | 74-78% | ✅ | 40+ languages | Apache 2.0 | Self-hosted ✅ |

**Primary Stack**: Llama-3.2 (zero API costs, full privacy). **Fallback**: EuroVLM-9B (EU-native multilingual support).
