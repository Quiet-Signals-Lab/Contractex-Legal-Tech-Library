"""
Pytest configuration and shared fixtures.

This file is automatically discovered by pytest and provides reusable fixtures
for all test files.
"""
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

# Try to import psycopg2, but allow tests to run without it for unit tests
try:
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False
    psycopg2 = None  # type: ignore
    ISOLATION_LEVEL_AUTOCOMMIT = None

from contractex.storage.config import get_db_config
from contractex.storage.models import (
    Clause,
    Document,
    ProcessingLog,
    ProcessingStage,
    ProcessingStatus,
)

# Conditionally import repository classes
if PSYCOPG2_AVAILABLE:
    from contractex.storage.repository import (
        ClauseRepository,
        DocumentRepository,
        ProcessingLogRepository,
    )


def _postgres_available() -> bool:
    """Check if PostgreSQL is available for integration tests."""
    if not PSYCOPG2_AVAILABLE:
        return False
    try:
        config = get_db_config()
        conn = psycopg2.connect(
            dbname='postgres',
            user=config['user'],
            password=config['password'],
            host=config['host'],
            port=config['port'],
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        return False


POSTGRES_AVAILABLE = _postgres_available()


def pytest_collection_modifyitems(config, items):
    """Skip integration tests if PostgreSQL is not available."""
    if POSTGRES_AVAILABLE:
        return
    skip_integration = pytest.mark.skip(reason="PostgreSQL not available")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


# ============================================================================
# Configuration Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def test_db_config():
    """Test database configuration (separate from production)."""
    config = get_db_config()
    config['db_name'] = 'clause_docs_test'  # Use test database
    return config


@pytest.fixture(scope="session")
def db_schema_sql():
    """Load schema SQL for test database setup."""
    import pathlib
    schema_file = pathlib.Path(__file__).parent.parent / "contractex" / "storage" / "schema.sql"
    with open(schema_file) as f:
        # Skip database creation and extension lines
        lines = f.readlines()
        sql_lines = []
        skip_until_blank = False
        for line in lines:
            if line.strip().startswith('-- CREATE DATABASE') or line.strip().startswith('-- CREATE EXTENSION'):
                skip_until_blank = True
            if skip_until_blank and line.strip() == '':
                skip_until_blank = False
                continue
            if not skip_until_blank and not line.strip().startswith('-- CREATE'):
                sql_lines.append(line)
        return ''.join(sql_lines)


# ============================================================================
# Database Fixtures (Integration Tests)
# ============================================================================

@pytest.fixture(scope="session")
def test_database(test_db_config, db_schema_sql):
    """
    Create test database once per test session.

    This fixture creates a separate test database to avoid affecting
    production data. It's created once and reused for all tests.
    """
    if not PSYCOPG2_AVAILABLE:
        pytest.skip("psycopg2 not installed - integration tests require PostgreSQL")

    # Connect to postgres database to create test database
    conn = psycopg2.connect(
        dbname='postgres',
        user=test_db_config['user'],
        password=test_db_config['password'],
        host=test_db_config['host'],
        port=test_db_config['port']
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()

    # Drop and create test database
    db_name = test_db_config['db_name']
    cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")
    cursor.execute(f"CREATE DATABASE {db_name} ENCODING 'UTF8'")
    cursor.close()
    conn.close()

    # Connect to test database and create schema
    test_conn = psycopg2.connect(
        dbname=test_db_config['db_name'],
        user=test_db_config['user'],
        password=test_db_config['password'],
        host=test_db_config['host'],
        port=test_db_config['port']
    )
    test_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = test_conn.cursor()
    cursor.execute(db_schema_sql)
    cursor.close()
    test_conn.close()

    yield test_db_config

    # Teardown: Drop test database after all tests
    conn = psycopg2.connect(
        dbname='postgres',
        user=test_db_config['user'],
        password=test_db_config['password'],
        host=test_db_config['host'],
        port=test_db_config['port']
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute(f"DROP DATABASE IF EXISTS {db_name}")
    cursor.close()
    conn.close()


@pytest.fixture
def db_connection(test_database):
    """
    Provide a database connection for tests.

    Uses transaction rollback to ensure test isolation - each test gets
    a clean database state.
    """
    conn = psycopg2.connect(
        dbname=test_database['db_name'],
        user=test_database['user'],
        password=test_database['password'],
        host=test_database['host'],
        port=test_database['port']
    )

    yield conn

    # Rollback transaction to clean up test data
    conn.rollback()
    conn.close()


@pytest.fixture
def clean_db(db_connection):
    """
    Clean database before each test.

    Truncates all tables to ensure test isolation.
    """
    cursor = db_connection.cursor()
    cursor.execute("TRUNCATE documents, clauses, processing_log CASCADE")
    db_connection.commit()
    yield db_connection


# ============================================================================
# Repository Fixtures
# ============================================================================

@pytest.fixture
def doc_repo(clean_db):
    """Document repository with clean database."""
    with patch('contractex.storage.repository.get_cursor') as mock_cursor:
        # Make mock_cursor return a context manager that yields the real cursor
        def cursor_context(*args, **kwargs):
            from contextlib import contextmanager
            @contextmanager
            def _cursor():
                cur = clean_db.cursor()
                try:
                    yield cur
                    clean_db.commit()
                finally:
                    cur.close()
            return _cursor()

        mock_cursor.side_effect = cursor_context
        yield DocumentRepository()


@pytest.fixture
def clause_repo(clean_db):
    """Clause repository with clean database."""
    with patch('contractex.storage.repository.get_cursor') as mock_cursor:
        def cursor_context(*args, **kwargs):
            from contextlib import contextmanager
            @contextmanager
            def _cursor():
                cur = clean_db.cursor()
                try:
                    yield cur
                    clean_db.commit()
                finally:
                    cur.close()
            return _cursor()

        mock_cursor.side_effect = cursor_context
        yield ClauseRepository()


@pytest.fixture
def log_repo(clean_db):
    """Processing log repository with clean database."""
    with patch('contractex.storage.repository.get_cursor') as mock_cursor:
        def cursor_context(*args, **kwargs):
            from contextlib import contextmanager
            @contextmanager
            def _cursor():
                cur = clean_db.cursor()
                try:
                    yield cur
                    clean_db.commit()
                finally:
                    cur.close()
            return _cursor()

        mock_cursor.side_effect = cursor_context
        yield ProcessingLogRepository()


# ============================================================================
# Model Fixtures (Test Data)
# ============================================================================

@pytest.fixture
def sample_document():
    """Sample document for testing."""
    return Document(
        filename="test_contract.pdf",
        file_hash="a1b2c3d4e5f6",
        file_data=b"PDF binary data",
        extracted_text="This is a test contract agreement...",
        metadata={
            "contract_type": "NDA",
            "parties": ["Company A", "Company B"],
            "effective_date": "2024-01-01",
            "expiration_date": "2026-01-01",
            "governing_law": "Delaware"
        }
    )


@pytest.fixture
def sample_clause():
    """Sample clause for testing."""
    return Clause(
        document_id=1,
        clause_text="Party A shall pay Party B $10,000 within 30 days.",
        clause_type="payment",
        page_number=3,
        bbox_x=50.0,
        bbox_y=200.0,
        bbox_width=500.0,
        bbox_height=50.0,
        confidence_score=0.95,
        metadata={"amount": 10000, "currency": "USD"}
    )


@pytest.fixture
def sample_processing_log():
    """Sample processing log for testing."""
    return ProcessingLog(
        document_id=1,
        processing_stage=ProcessingStage.UPLOADED,
        status=ProcessingStatus.COMPLETED,
        error_message=None
    )


@pytest.fixture
def multiple_documents():
    """Multiple sample documents for testing queries."""
    return [
        Document(
            filename=f"contract_{i}.pdf",
            file_hash=f"hash_{i}",
            extracted_text=f"Contract {i} text",
            metadata={
                "contract_type": "NDA" if i % 2 == 0 else "MSA",
                "parties": [f"Company {chr(65+i)}", f"Company {chr(66+i)}"],
                "effective_date": f"2024-{i+1:02d}-01"
            }
        )
        for i in range(5)
    ]


@pytest.fixture
def multiple_clauses():
    """Multiple sample clauses for testing."""
    clause_types = ["payment", "termination", "confidentiality", "liability"]
    return [
        Clause(
            document_id=1,
            clause_text=f"Clause {i} text with {clause_types[i % 4]} content.",
            clause_type=clause_types[i % 4],
            page_number=(i % 10) + 1,
            confidence_score=0.8 + (i * 0.02)
        )
        for i in range(10)
    ]


# ============================================================================
# Mock Fixtures (Unit Tests)
# ============================================================================

@pytest.fixture
def mock_cursor():
    """Mock database cursor for unit tests."""
    cursor = MagicMock()
    cursor.fetchone.return_value = (1, "test.pdf", "hash123", b"data", "text", {}, datetime.now(), datetime.now())
    cursor.fetchall.return_value = []
    return cursor


@pytest.fixture
def mock_connection():
    """Mock database connection for unit tests."""
    conn = MagicMock()
    conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests that don't require database"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests that require database"
    )
    config.addinivalue_line(
        "markers", "slow: Slow tests that may take longer to run"
    )


# ============================================================================
# Helper Functions
# ============================================================================

@pytest.fixture
def assert_document_equal():
    """Helper fixture to compare documents."""
    def _assert_equal(doc1: Document, doc2: Document, ignore_timestamps=True):
        assert doc1.filename == doc2.filename
        assert doc1.file_hash == doc2.file_hash
        assert doc1.extracted_text == doc2.extracted_text
        assert doc1.metadata == doc2.metadata
        if not ignore_timestamps:
            assert doc1.uploaded_at == doc2.uploaded_at
            assert doc1.updated_at == doc2.updated_at
    return _assert_equal
