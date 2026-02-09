# Database Layer (`dbase`)

The database layer provides structured access to legal document data, implementing a clean separation between storage and business logic through the repository pattern.

## Architecture Overview

Following best practices for legal tech document analysis systems, this module implements:

- **Minimal Viable Schema**: Three core tables (documents, clauses, processing_log) with room to grow
- **Repository Pattern**: Clean API that hides SQL complexity
- **Context Managers**: Automatic connection lifecycle management
- **Deferred Optimization**: Embeddings tables not yet created (build when needed)
- **Metadata-First**: JSONB columns for flexible legal document attributes

## Quick Start

### 1. Setup Database

```bash
# Initialize database, schema, and load CUAD data
python -m dbase.setup

# Setup without loading data
python -m dbase.setup --no-data

# Setup with limited data (for testing)
python -m dbase.setup --limit 10
```

### 2. Basic Usage

```python
from dbase import DocumentRepository, Document, ClauseRepository, Clause

# Create document
doc = Document(
    filename="contract.pdf",
    extracted_text="This agreement...",
    metadata={
        "contract_type": "NDA",
        "parties": ["Company A", "Company B"],
        "effective_date": "2024-01-01",
        "governing_law": "New York"
    }
)

# Store document
repo = DocumentRepository()
doc_id = repo.insert(doc)

# Add clauses
clauses = [
    Clause(
        document_id=doc_id,
        clause_text="Party A agrees to...",
        clause_type="payment",
        page_number=1,
        confidence_score=0.95
    ),
    Clause(
        document_id=doc_id,
        clause_text="This agreement terminates...",
        clause_type="termination",
        page_number=5
    )
]

clause_repo = ClauseRepository()
clause_ids = clause_repo.insert_batch(clauses)
```

### 3. Querying

```python
# Find by ID
doc = repo.get_by_id(doc_id)

# Search by metadata
ndas = repo.search_by_metadata({"contract_type": "NDA"})

# Get all clauses from document
doc_clauses = clause_repo.get_by_document(doc_id)

# Find all payment clauses
payment_clauses = clause_repo.search_by_type("payment")
```

## Schema Design

### Documents Table
Central registry for source files with flexible metadata.

**Key Fields:**
- `filename`: Unique identifier
- `file_hash`: SHA-256 for deduplication
- `file_data`: Binary storage (BYTEA)
- `extracted_text`: Extracted content
- `metadata`: JSONB for legal attributes (contract_type, parties, dates, etc.)

### Clauses Table
Extracted text segments with spatial and hierarchical structure.

**Key Fields:**
- `document_id`: Foreign key to documents
- `clause_text`: Extracted text
- `clause_type`: Classification (payment, termination, etc.)
- `page_number`, `bbox_*`: Visual grounding coordinates
- `confidence_score`: Extraction model confidence
- `parent_clause_id`: For hierarchical clauses

### Processing Log Table
Audit trail for document lifecycle.

**Key Fields:**
- `document_id`: Foreign key to documents
- `processing_stage`: uploaded, extracted, embedded, indexed
- `status`: pending, completed, failed
- `error_message`: Debugging information

## Metadata Strategy

Use consistent, controlled vocabularies for metadata fields:

```python
# Good: Standardized contract type
metadata = {
    "contract_type": "NDA",  # Use controlled vocabulary
    "parties": ["Acme Corp", "Beta LLC"],
    "effective_date": "2024-01-01",  # ISO format
    "expiration_date": "2025-01-01",
    "governing_law": "New York",
    "custom_tags": ["vendor", "high-value"]
}

# Bad: Inconsistent values fragment your data
metadata = {
    "contract_type": "nda",  # lowercase
    "parties": "Acme Corp, Beta LLC",  # string instead of array
    "effective_date": "Jan 1 2024",  # non-standard format
}
```

## Repository Pattern Benefits

Repositories provide a clean abstraction:

```python
# Application code never writes SQL
doc_repo = DocumentRepository()
doc_id = doc_repo.insert(doc)  # Clean API

# Easy to test with mocks
class MockDocumentRepository:
    def insert(self, doc):
        return 123  # Mock ID

# Database-agnostic - swap PostgreSQL for another backend
# by implementing the same repository interface
```

## What's NOT Implemented Yet

Following the principle of **building only what's needed now**, these features are deferred:

- ❌ **Embeddings**: No vector columns yet - add when implementing RAG retrieval
- ❌ **Full-text Search**: No tsvector indexes - may not need if using vector search
- ❌ **User Authentication**: No users/roles tables until multi-user requirements
- ❌ **Audit Trails**: Processing_log sufficient for development
- ❌ **Document Images**: No page-level image table until vision features needed

## Future Enhancements

When ready, extend with:

### Embeddings (for RAG)
```sql
-- Add to clauses table OR create separate table
ALTER TABLE clauses ADD COLUMN text_embedding VECTOR(1536);
ALTER TABLE clauses ADD COLUMN vision_embedding VECTOR(512);

CREATE INDEX ON clauses USING ivfflat (text_embedding vector_cosine_ops);
```

### Document Images (for vision)
```sql
CREATE TABLE document_images (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id),
    page_number INTEGER,
    image_data BYTEA,
    vision_embedding VECTOR(768),
    layout_type VARCHAR(50)
);
```

### Multi-user Support
```sql
ALTER TABLE documents ADD COLUMN owner_id INTEGER REFERENCES users(id);
ALTER TABLE documents ADD COLUMN permissions JSONB;
```

## Configuration

Set environment variables for production:

```bash
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=your_user
export POSTGRES_DB=clause_docs
export POSTGRES_PASSWORD=your_password
export LOG_LEVEL=INFO
```

## Testing Connection

```python
from dbase.connection import test_connection

if test_connection():
    print("Database connected successfully!")
```

## Module Structure

```
dbase/
├── __init__.py          # Public API exports
├── config.py            # Configuration with env var support
├── connection.py        # Connection management & context managers
├── models.py            # Domain objects (Document, Clause, ProcessingLog)
├── repository.py        # Repository pattern implementations
├── schema.sql           # Database schema (idempotent)
├── setup.py             # One-time initialization script
└── README.md            # This file
```

## Best Practices

1. **Use repositories, not raw SQL** in application code
2. **Standardize metadata fields** - use controlled vocabularies
3. **Log processing stages** - insert ProcessingLog entries for audit trail
4. **Use context managers** - `with get_connection()` handles cleanup
5. **Batch insert clauses** - use `insert_batch()` for performance
6. **Index JSONB** - GIN indexes make metadata queries fast

## Troubleshooting

**Connection fails:**
```python
from dbase.connection import test_connection
test_connection()  # Returns False and logs error details
```

**Database doesn't exist:**
```bash
python -m dbase.setup  # Creates database and schema
```

**Check what's in database:**
```python
from dbase import DocumentRepository, ClauseRepository

doc_repo = DocumentRepository()
print(f"Documents: {doc_repo.count()}")

clause_repo = ClauseRepository()
print(f"Clauses for doc 1: {clause_repo.count_by_document(1)}")
```

## License

Part of the Contract Clause Extractor project.
