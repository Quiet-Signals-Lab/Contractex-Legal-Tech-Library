"""
Local LLM Example - Privacy-First Deployment

Run contract extraction completely locally using Ollama,
perfect for sensitive documents and data privacy requirements.
"""

from contractex import ContractExtractor
from contractex.llm import LocalProvider

# Configure local LLM (requires Ollama running locally)
# First, pull the model: ollama pull llama-3.1-70b
llm = LocalProvider(
    model="llama-3.1-70b",  # Or llama-3-8b for faster processing
    host="http://localhost:11434",
    temperature=0.0,
    max_tokens=4000
)

# Create extractor with local LLM
extractor = ContractExtractor(
    llm_provider=llm,
    confidence_threshold=0.7
)

print("Extracting contract using local LLM (100% private)...")

# Extract contract - all processing happens locally
contract = extractor.extract(
    "sensitive_contract.pdf",
    analyze_risks=True,
    extract_financial=True
)

print(f"\n=== Extraction Complete ===")
print(f"Contract Type: {contract.contract_type}")
print(f"Parties: {', '.join([p.name for p in contract.parties])}")
print(f"Clauses: {len(contract.clauses)}")
print(f"Risks: {len(contract.risks)}")

# Cost is $0 for local models
print(f"\nAPI Cost: $0.00 (local processing)")
print(f"Processing Time: {contract.metadata.processing_time_seconds:.2f}s")

# Export results
contract.to_json("private_extraction.json")

print("\n✓ Contract processed completely locally")
print("✓ No data sent to external APIs")
print("✓ Full data privacy and sovereignty")

# Benefits of local LLM:
# - Zero API costs
# - Complete data privacy
# - No rate limits
# - Works offline
# - Data sovereignty compliance (GDPR, HIPAA, etc.)

# Trade-offs:
# - Slower processing (depending on hardware)
# - Requires powerful local hardware (GPU recommended)
# - May have lower accuracy than GPT-4/Claude for complex contracts
