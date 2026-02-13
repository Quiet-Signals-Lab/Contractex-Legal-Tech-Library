# Contributing to ContractEx

Thank you for your interest in contributing! ContractEx is a community-driven project and welcomes contributions of all kinds.

---

## Getting Started

### 1. Fork and Clone

```bash
git clone https://github.com/aahepburn/Contract-Clause-Extractor.git
cd Contract-Clause-Extractor
```

### 2. Set Up Your Development Environment

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
```

### 3. Configure API Keys (optional — unit tests don't require them)

```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY / ANTHROPIC_API_KEY
```

---

## Running Tests

```bash
# Unit tests only (no API keys or database required)
pytest tests/ -m unit -v

# All tests (requires PostgreSQL + API keys for integration tests)
pytest

# With coverage report
pytest --cov=contractex --cov-report=html
```

---

## Code Quality

All contributions must pass the following checks before merging:

```bash
black contractex/ tests/         # Formatting
ruff check contractex/ tests/    # Linting
mypy contractex/                 # Type checking
```

Run them all at once:

```bash
black contractex/ tests/ && ruff check contractex/ tests/ && mypy contractex/
```

---

## Contribution Guidelines

### Bugs

- Search [existing issues](https://github.com/aahepburn/Contract-Clause-Extractor/issues) before filing a new one.
- Include a minimal reproducible example and the full traceback.

### Features

- Open an issue first to discuss the feature before writing code — this avoids wasted effort.
- New LLM providers should extend `contractex.llm.base.LLMProvider` and implement all abstract methods including `_call_with_retry`.
- New clause types should be added to `contractex/taxonomy/cuad.py` and reflected in the prompt taxonomy in `contractex/prompts/clause_extraction.py`.

### Pull Requests

1. Branch from `main`: `git checkout -b feature/my-feature`
2. Write or update tests for your change (unit tests preferred).
3. Ensure all tests pass and code quality checks are clean.
4. Open a pull request with a clear description of _what_ and _why_.
5. Link the related issue if one exists.

---

## Project Structure

```
contractex/
├── core/           # Extraction, classification, risk analysis
├── llm/            # LLM provider implementations
├── loaders/        # Document loaders (PDF, DOCX, etc.)
├── chunking/       # Text chunking strategies
├── prompts/        # LLM prompt templates
├── storage/        # PostgreSQL + pgvector persistence
├── retrieval/      # Hybrid search & reranking
├── taxonomy/       # CUAD clause taxonomy
└── utils/          # Normalizers, validators, helpers
```

---

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add support for local Mistral models
fix: handle empty LLM response in clause extraction
docs: update quick-start example
test: add unit tests for deduplication logic
refactor: simplify ChunkingStrategy base class
```

---

## License

By contributing you agree that your contributions will be licensed under the [Apache 2.0 License](LICENSE).
