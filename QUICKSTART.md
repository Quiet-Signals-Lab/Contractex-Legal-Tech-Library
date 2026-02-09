# 🚀 Quick Start Guide: Database Layer Setup

This guide will get you up and running with the Contract Clause Extractor database in **under 5 minutes**.

---

## ✅ Prerequisites

- **Python 3.8+** installed
- **PostgreSQL 12+** installed and running
- **macOS** (for this guide - adjust commands for other OS)

---

## 📦 Step 1: Install PostgreSQL (if needed)

```bash
# Install PostgreSQL using Homebrew
brew install postgresql@14

# Start PostgreSQL service
brew services start postgresql@14

# Verify PostgreSQL is running
psql --version
# Expected output: psql (PostgreSQL) 14.x
```

---

## 🐍 Step 2: Install Python Dependencies

```bash
# From project root directory
cd /Users/aahepburn/Projects/Contract-Clause-Extractor

# Install database dependencies
pip install -r dbase/requirements.txt

# Or install directly:
pip install psycopg2-binary
```

---

## 🗄️ Step 3: Initialize Database

```bash
# Run the setup script (creates database, tables, and loads CUAD data)
python -m dbase.setup

# Expected output:
# ======================================================================
# Starting database setup
# ======================================================================
# Step 1: Creating database...
# Step 2: Setting up extensions...
# Step 3: Creating schema...
# Step 4: Ingesting initial data...
# Step 5: Verifying setup...
#   documents: 510 rows
#   clauses: 0 rows
#   processing_log: 510 rows
# ======================================================================
# Database setup completed successfully!
# ======================================================================
```

### Alternative Setup Options

```bash
# Setup without loading data (faster, for testing)
python -m dbase.setup --no-data

# Setup with limited data (useful for development)
python -m dbase.setup --limit 10
```

---

## ✅ Step 4: Verify Installation

```bash
# Run validation script
python3 validate_dbase.py

# Expected output:
# ✅ PASS: File Structure
# ✅ PASS: Imports
# ✅ PASS: Model Creation
# ✅ All validation tests passed!
```

---

## 🎯 Step 5: Run Example Code

```bash
# Run the database example demonstrating all features
python examples/dbase_example.py

# Expected output:
# ======================================================================
# Example 1: Document Operations
# ======================================================================
# Inserted document with ID: 511
# Retrieved: example_nda_2024.pdf
# Found 1 NDA documents
# Updated metadata
# 
# ======================================================================
# Example 2: Clause Operations
# ======================================================================
# Inserted 4 clauses
# Document has 4 clauses
# ...
```

---

## 💻 Your First Database Query

Create a file `test_db.py`:

```python
from dbase import DocumentRepository, Document

# Create a document
doc = Document(
    filename="my_first_contract.pdf",
    extracted_text="This is a test contract...",
    metadata={
        "contract_type": "NDA",
        "parties": ["Your Company", "Partner Company"],
        "effective_date": "2024-01-01"
    }
)

# Store in database
repo = DocumentRepository()
doc_id = repo.insert(doc)
print(f"✅ Document inserted with ID: {doc_id}")

# Retrieve it back
retrieved = repo.get_by_id(doc_id)
print(f"✅ Retrieved: {retrieved.filename}")
print(f"   Contract Type: {retrieved.metadata['contract_type']}")
print(f"   Parties: {retrieved.metadata['parties']}")

# Search by metadata
ndas = repo.search_by_metadata({"contract_type": "NDA"})
print(f"✅ Found {len(ndas)} NDA contracts in database")
```

Run it:
```bash
python test_db.py
```

---

## 🔧 Troubleshooting

### Problem: "psql: error: connection to server at "localhost" ... failed"

**Solution**: PostgreSQL is not running. Start it:
```bash
brew services start postgresql@14
```

### Problem: "FATAL: database 'clause_docs' does not exist"

**Solution**: Run the setup script:
```bash
python -m dbase.setup
```

### Problem: "ModuleNotFoundError: No module named 'psycopg2'"

**Solution**: Install dependencies:
```bash
pip install psycopg2-binary
```

### Problem: "permission denied for database 'clause_docs'"

**Solution**: Update database config with your PostgreSQL user:
```bash
export POSTGRES_USER=your_username
export POSTGRES_PASSWORD=your_password
python -m dbase.setup
```

### Problem: Want to start fresh?

**Solution**: Drop and recreate database:
```bash
# Connect to PostgreSQL
psql postgres

# Drop database (at postgres=# prompt)
DROP DATABASE IF EXISTS clause_docs;
\q

# Re-run setup
python -m dbase.setup
```

---

## 🧪 Testing Connection

Quick test to verify database is accessible:

```python
from dbase.connection import test_connection

if test_connection():
    print("✅ Database connection successful!")
else:
    print("❌ Database connection failed")
```

Or from command line:
```bash
python -c "from dbase.connection import test_connection; print('✅ Connected!' if test_connection() else '❌ Connection failed')"
```

---

## 📚 What's Next?

Now that your database is set up:

1. **Explore the schema**: Check out [dbase/schema.sql](dbase/schema.sql)
2. **Read the docs**: See [dbase/README.md](dbase/README.md) for detailed API documentation
3. **Review examples**: Study [examples/dbase_example.py](examples/dbase_example.py)
4. **Integration**: Connect your document extraction pipeline to the database
5. **Customize metadata**: Add your own metadata fields to documents
6. **Build features**: Implement clause extraction and classification

---

## 🎓 Key Concepts Recap

- **Documents Table**: Central registry for all contracts and legal documents
- **Clauses Table**: Extracted text segments with classification and spatial data
- **Processing Log**: Audit trail tracking document lifecycle stages
- **Repository Pattern**: Clean API - `repo.insert(doc)` instead of raw SQL
- **Metadata**: Flexible JSONB columns for legal document attributes
- **Idempotent Setup**: Safe to re-run `python -m dbase.setup` anytime

---

## 📖 Configuration

The database uses environment variables for configuration:

```bash
# Optional: Set custom configuration
export POSTGRES_HOST=localhost
export POSTGRES_PORT=5432
export POSTGRES_USER=aahepburn
export POSTGRES_DB=clause_docs
export POSTGRES_PASSWORD=your_password

# Then run setup
python -m dbase.setup
```

Default values are in [dbase/config.py](dbase/config.py).

---

## 🎉 Success Criteria

You're all set when:

- ✅ `python -m dbase.setup` completes without errors
- ✅ `python3 validate_dbase.py` shows all tests passing
- ✅ `python examples/dbase_example.py` runs successfully
- ✅ You can create and retrieve documents with the repository API

---

**Happy Coding! 🚀**

For detailed architecture documentation, see [DATABASE_IMPLEMENTATION.md](DATABASE_IMPLEMENTATION.md).
