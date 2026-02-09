# Test Suite for Database Layer

Comprehensive test suite for the Contract Clause Extractor database module, using pytest with both unit and integration tests.

## 📁 Test Structure

```
tests/
├── __init__.py                      # Test package initialization
├── conftest.py                      # Shared fixtures and pytest configuration
├── test_models.py                   # Unit tests for domain models
├── test_repository_integration.py   # Integration tests for repositories
├── test_connection_config.py        # Connection and config tests
├── test_smoke.py                    # Quick smoke tests for CI
├── requirements.txt                 # Test dependencies
└── README.md                        # This file
```

## 🚀 Quick Start

### 1. Install Test Dependencies

```bash
# Install core dependencies first
pip install -r dbase/requirements.txt

# Install test dependencies
pip install -r tests/requirements.txt
```

### 2. Run All Tests

```bash
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run with coverage
pytest --cov=dbase --cov-report=html

# View coverage report
open htmlcov/index.html
```

### 3. Run Specific Test Categories

```bash
# Unit tests only (no database required)
pytest -m unit

# Integration tests only (requires database)
pytest -m integration

# Smoke tests only (fast CI tests)
pytest -m smoke

# Slow tests
pytest -m "not slow"
```

## 🧪 Test Categories

### Unit Tests (`-m unit`)
- **No database required**
- Test domain models in isolation
- Test business logic
- Fast execution
- Files: `test_models.py`, parts of `test_connection_config.py`

### Integration Tests (`-m integration`)
- **Requires PostgreSQL database**
- Test full stack with real database
- Test repository operations
- Slower execution
- Files: `test_repository_integration.py`

### Smoke Tests (`-m smoke`)
- **Fast verification tests**
- Verify imports and basic functionality
- Ideal for CI/CD pipelines
- Files: `test_smoke.py`

## 📝 Running Specific Tests

```bash
# Run single test file
pytest tests/test_models.py

# Run single test class
pytest tests/test_models.py::TestDocumentModel

# Run single test method
pytest tests/test_models.py::TestDocumentModel::test_document_creation

# Run tests matching pattern
pytest -k "test_document"

# Run with specific markers
pytest -m "unit and not slow"
```

## 🔧 Advanced Options

### Parallel Execution

```bash
# Run tests in parallel (faster)
pytest -n auto
```

### Verbose Output

```bash
# Show print statements
pytest -v -s

# Show local variables in failures
pytest --showlocals

# Show full diff on assertion failures
pytest -vv
```

### Stop on First Failure

```bash
pytest -x              # Stop on first failure
pytest --maxfail=3     # Stop after 3 failures
```

### Re-run Failed Tests

```bash
# Run only failed tests from last run
pytest --lf

# Run failed tests first, then others
pytest --ff
```

## 📊 Coverage Reporting

```bash
# Generate HTML coverage report
pytest --cov=dbase --cov-report=html

# Generate terminal coverage report
pytest --cov=dbase --cov-report=term

# Generate XML coverage report (for CI)
pytest --cov=dbase --cov-report=xml

# Show missing lines
pytest --cov=dbase --cov-report=term-missing
```

## 🗄️ Database Setup for Integration Tests

Integration tests automatically create and destroy a test database. Requirements:

1. **PostgreSQL must be running**
   ```bash
   brew services start postgresql@14
   ```

2. **User must have database creation privileges**
   ```bash
   # Grant privileges if needed
   psql postgres -c "ALTER USER aahepburn CREATEDB;"
   ```

3. **Test database is automatically managed**
   - Created: `clause_docs_test`
   - Destroyed after tests complete
   - Isolated from production `clause_docs` database

### Manual Database Cleanup

If tests fail and leave test database:
```bash
psql postgres -c "DROP DATABASE IF EXISTS clause_docs_test;"
```

## 🎯 Writing New Tests

### Unit Test Example

```python
# tests/test_my_feature.py
import pytest
from dbase.models import Document

@pytest.mark.unit
class TestMyFeature:
    """Unit tests for my feature."""
    
    def test_something(self, sample_document):
        """Test description."""
        assert sample_document.filename == "test_contract.pdf"
```

### Integration Test Example

```python
@pytest.mark.integration
class TestMyIntegration:
    """Integration tests requiring database."""
    
    def test_with_database(self, doc_repo, sample_document):
        """Test with real database."""
        doc_id = doc_repo.insert(sample_document)
        assert doc_id > 0
```

## 🔍 Available Fixtures

From `conftest.py`:

### Database Fixtures
- `test_database` - Test database config
- `db_connection` - Database connection
- `clean_db` - Clean database for each test

### Repository Fixtures
- `doc_repo` - DocumentRepository instance
- `clause_repo` - ClauseRepository instance
- `log_repo` - ProcessingLogRepository instance

### Model Fixtures
- `sample_document` - Sample Document instance
- `sample_clause` - Sample Clause instance
- `sample_processing_log` - Sample ProcessingLog instance
- `multiple_documents` - List of Documents
- `multiple_clauses` - List of Clauses

### Mock Fixtures
- `mock_cursor` - Mock database cursor
- `mock_connection` - Mock database connection

### Helper Fixtures
- `assert_document_equal` - Compare Document instances

## 🐛 Debugging Tests

### Run with Debugger

```bash
# Drop into debugger on failure
pytest --pdb

# Drop into debugger at start of test
pytest --trace
```

### Increase Verbosity

```bash
# Show all output
pytest -vv -s --tb=long

# Show full traceback
pytest --tb=long
```

### Test Specific Issue

```pybash
# Isolate and debug one test
pytest tests/test_models.py::TestDocumentModel::test_document_creation -vv -s --pdb
```

## 📈 Continuous Integration

### GitHub Actions Example

```yaml
name: Tests
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      postgres:
        image: postgres:14
        env:
          POSTGRES_PASSWORD: postgres
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install -r dbase/requirements.txt
          pip install -r tests/requirements.txt
      
      - name: Run smoke tests
        run: pytest -m smoke
      
      - name: Run unit tests
        run: pytest -m unit --cov=dbase
      
      - name: Run integration tests
        env:
          POSTGRES_HOST: localhost
          POSTGRES_USER: postgres
          POSTGRES_PASSWORD: postgres
        run: pytest -m integration
```

## 🏆 Best Practices

1. **Mark your tests appropriately**
   ```python
   @pytest.mark.unit  # or @pytest.mark.integration
   ```

2. **Use fixtures for setup**
   ```python
   def test_something(sample_document, doc_repo):
       # Fixtures handle setup/teardown
   ```

3. **Write descriptive test names**
   ```python
   def test_document_insertion_with_duplicate_filename():
       # Clear what's being tested
   ```

4. **One assertion concept per test**
   - Test one thing well
   - Multiple asserts OK if testing same concept

5. **Arrange-Act-Assert pattern**
   ```python
   def test_example():
       # Arrange
       doc = Document(filename="test.pdf")
       
       # Act
       result = doc_repo.insert(doc)
       
       # Assert
       assert result > 0
   ```

## 📊 Test Coverage Goals

- **Overall Coverage**: > 85%
- **Critical Modules** (models, repository): > 90%
- **Configuration/Setup**: > 70%

Check current coverage:
```bash
pytest --cov=dbase --cov-report=term-missing
```

## 🚨 Troubleshooting

### Tests Fail to Connect to Database

```bash
# Check PostgreSQL is running
brew services list | grep postgres

# Start if needed
brew services start postgresql@14
```

### Test Database Already Exists

```bash
# Clean up manually
psql postgres -c "DROP DATABASE IF EXISTS clause_docs_test;"
```

### Import Errors

```bash
# Ensure you're in project root
cd /Users/aahepburn/Projects/Contract-Clause-Extractor

# Reinstall dependencies
pip install -r dbase/requirements.txt
pip install -r tests/requirements.txt
```

### Fixtures Not Found

Make sure `conftest.py` is in the `tests/` directory - pytest automatically discovers it.

## 📚 Additional Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest Fixtures](https://docs.pytest.org/en/stable/fixture.html)
- [Pytest Markers](https://docs.pytest.org/en/stable/mark.html)
- [Database Testing Guide](../dbase/README.md)

## 🎓 Test Statistics

Run this to see test statistics:

```bash
pytest --collect-only    # Show what tests will run
pytest --durations=10    # Show 10 slowest tests
pytest -v | grep -c PASSED  # Count passed tests
```

## ✅ Pre-commit Checklist

Before committing code:

```bash
# 1. Run all tests
pytest

# 2. Check coverage
pytest --cov=dbase --cov-report=term

# 3. Run smoke tests
pytest -m smoke

# 4. Check for warnings
pytest -W error::UserWarning
```

---

**Happy Testing! 🧪**
