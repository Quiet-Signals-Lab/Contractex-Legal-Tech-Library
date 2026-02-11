"""
Basic Contract Extraction Example

This example demonstrates the simplest way to use ContractEx:
extract a contract with a single line of code.
"""

from contractex import extract_contract

# Extract contract with default settings
contract = extract_contract("path/to/contract.pdf")

# Access the results
print(f"Contract Type: {contract.contract_type}")
print("\nParties:")
for party in contract.parties:
    print(f"  - {party.name} ({party.role})")

print(f"\nClauses: {len(contract.clauses)}")
for clause in contract.clauses[:5]:  # Show first 5
    print(f"  - {clause.clause_type}: {clause.text[:100]}...")

print(f"\nFinancial Terms: {len(contract.financial_terms)}")
for term in contract.financial_terms:
    print(f"  - {term.term_type}: {term.currency} {term.amount}")

print(f"\nRisks: {len(contract.risks)}")
for risk in contract.risks:
    print(f"  - [{risk.severity}] {risk.risk_type}: {risk.description}")

# Export results
contract.to_json("output.json")
contract.to_excel("output.xlsx")

print("\nResults saved to output.json and output.xlsx")
