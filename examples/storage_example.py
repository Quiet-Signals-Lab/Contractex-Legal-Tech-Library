"""
Storage Integration Example

This example demonstrates how to use the optional storage module to persist
extracted contract data in PostgreSQL.

Prerequisites:
    pip install contractex[storage]
    
    Set up PostgreSQL:
    - Install PostgreSQL
    - Create database: CREATE DATABASE contracts;
    - Set environment variables:
        export POSTGRES_HOST=localhost
        export POSTGRES_PORT=5432
        export POSTGRES_USER=postgres
        export POSTGRES_PASSWORD=yourpassword
        export POSTGRES_DB=contracts
"""

from contractex import extract_contract
from contractex.storage import DocumentRepository, ClauseRepository, Document, Clause
from contractex.storage.setup import setup_database
import os

def main():
    # Initialize database (run once)
    print("Setting up database...")
    try:
        setup_database()
        print("✓ Database initialized")
    except Exception as e:
        print(f"Database setup: {e} (may already exist)")
    
    # Extract contract
    contract_path = "data/CUAD_v1/full_contract_txt/ACCURAYINC_09_01_2010-EX-10.31-DISTRIBUTOR AGREEMENT.txt"
    
    if not os.path.exists(contract_path):
        print(f"Contract file not found: {contract_path}")
        print("Using a sample contract instead...")
        contract_path = "sample.pdf"  # Use your own contract
    
    print(f"\nExtracting contract from {contract_path}...")
    contract = extract_contract(contract_path)
    
    print(f"✓ Extracted: {contract.title}")
    print(f"  Parties: {len(contract.parties)}")
    print(f"  Clauses: {len(contract.clauses)}")
    
    # Store in database
    print("\nStoring in database...")
    
    # Create document record
    doc = Document(
        filename=os.path.basename(contract_path),
        extracted_text=" ".join([c.text for c in contract.clauses]),  # Combined text
        metadata={
            "title": contract.title,
            "parties": [{"name": p.name, "role": p.role} for p in contract.parties],
            "effective_date": contract.metadata.extracted_at.isoformat() if contract.metadata else None,
            "clause_count": len(contract.clauses),
        }
    )
    
    doc_repo = DocumentRepository()
    doc_id = doc_repo.insert(doc)
    print(f"✓ Document stored with ID: {doc_id}")
    
    # Store clauses
    clause_repo = ClauseRepository()
    clause_ids = []
    
    for clause in contract.clauses[:10]:  # Store first 10 clauses as example
        db_clause = Clause(
            document_id=doc_id,
            clause_text=clause.text,
            clause_type=clause.cuad_type.value if clause.cuad_type else None,
            start_page=1,  # Would come from document parser
            end_page=1,
            confidence_score=clause.confidence,
            metadata={
                "cuad_type": clause.cuad_type.value if clause.cuad_type else None,
                "section": clause.section,
            }
        )
        clause_id = clause_repo.insert(db_clause)
        clause_ids.append(clause_id)
    
    print(f"✓ Stored {len(clause_ids)} clauses")
    
    # Query back from database
    print("\nQuerying from database...")
    
    # Get document
    retrieved_doc = doc_repo.get_by_id(doc_id)
    print(f"✓ Retrieved document: {retrieved_doc.filename}")
    
    # Search clauses by type
    if contract.clauses[0].cuad_type:
        clause_type = contract.clauses[0].cuad_type.value
        matching_clauses = clause_repo.search_by_clause_type(clause_type)
        print(f"✓ Found {len(matching_clauses)} clauses of type '{clause_type}'")
    
    # Get all documents
    all_docs = doc_repo.get_all(limit=5)
    print(f"\n✓ Total documents in database: {len(all_docs)}")
    for doc in all_docs:
        print(f"  - {doc.filename} (ID: {doc.id})")
    
    print("\n✓ Storage example complete!")
    print("\nNext steps:")
    print("  - Use storage for contract versioning")
    print("  - Query contracts by metadata")
    print("  - Build search indices on clauses")
    print("  - Integrate with retrieval module (future)")


if __name__ == "__main__":
    try:
        main()
    except ImportError as e:
        print("Error: Storage module not installed")
        print("Install with: pip install contractex[storage]")
        print(f"Details: {e}")
    except Exception as e:
        print(f"Error: {e}")
        print("\nTroubleshooting:")
        print("  1. Ensure PostgreSQL is running")
        print("  2. Check environment variables (POSTGRES_HOST, etc.)")
        print("  3. Verify database exists: CREATE DATABASE contracts;")
