"""
Batch Processing Example

Process multiple contracts in parallel for efficiency.
"""

from pathlib import Path

from contractex import ContractExtractor

# Initialize extractor
extractor = ContractExtractor(
    llm_provider_name="gpt-4o",
    confidence_threshold=0.7
)

# Get list of contract files
contract_dir = Path("path/to/contracts")
contract_files = list(contract_dir.glob("*.pdf"))

print(f"Processing {len(contract_files)} contracts...")

# Method 1: Built-in batch processing
contracts = extractor.extract_batch(
    document_paths=[str(f) for f in contract_files],
    max_workers=4
)

print(f"Extracted {len(contracts)} contracts")

# Generate summary report
print("\n=== Batch Processing Summary ===\n")

for i, contract in enumerate(contracts, 1):
    print(f"{i}. {contract.metadata.filename}")
    print(f"   Type: {contract.contract_type}")
    print(f"   Parties: {', '.join([p.name for p in contract.parties])}")
    print(f"   Clauses: {len(contract.clauses)}")
    print(f"   Risks: {len(contract.risks)} ({len(contract.critical_risks)} critical)")
    print(f"   Confidence: {contract.metadata.overall_confidence:.2%}")
    print()

# Export all contracts to Excel
from contractex.utils.exporters import ExcelExporter

ExcelExporter.export_batch(contracts, "batch_results.xlsx")
print("Results exported to batch_results.xlsx")

# Create summary statistics
total_clauses = sum(len(c.clauses) for c in contracts)
total_risks = sum(len(c.risks) for c in contracts)
total_critical = sum(len(c.critical_risks) for c in contracts)

print("\n=== Statistics ===")
print(f"Total contracts: {len(contracts)}")
print(f"Total clauses extracted: {total_clauses}")
print(f"Total risks identified: {total_risks}")
print(f"Critical risks: {total_critical}")
