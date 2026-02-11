"""
Advanced Contract Extraction Example

This example shows how to customize the extraction process with:
- Custom LLM provider
- Custom document loader
- Custom chunking strategy
- Advanced configuration
"""

from contractex import ContractExtractor
from contractex.chunking import ClauseAwareChunker
from contractex.core.analyzers import RiskAnalyzer
from contractex.core.classifiers import CUADClassifier
from contractex.llm import OpenAIProvider
from contractex.loaders import PDFLoader

# Configure custom LLM provider
llm = OpenAIProvider(
    model="gpt-4o",
    temperature=0.0,
    max_tokens=4000
)

# Or use Anthropic
# llm = AnthropicProvider(
#     model="claude-3-5-sonnet-20241022",
#     temperature=0.0
# )

# Configure document loader with OCR
loader = PDFLoader(
    ocr_enabled=True,
    preserve_layout=True,
    extract_images=False
)

# Configure chunking strategy
chunker = ClauseAwareChunker(
    max_chunk_size=4000,
    overlap=200,
    preserve_sentences=True
)

# Create extractor with custom components
extractor = ContractExtractor(
    llm_provider=llm,
    document_loader=loader,
    chunking_strategy=chunker,
    confidence_threshold=0.8,
    parallel_processing=True
)

# Extract with custom options
contract = extractor.extract(
    "path/to/contract.pdf",
    analyze_risks=True,
    extract_financial=True
)

print(f"Extracted contract: {contract.contract_type}")
print(f"Overall confidence: {contract.metadata.overall_confidence:.2%}")
print(f"Processing time: {contract.metadata.processing_time_seconds:.2f}s")

# Custom clause classification
classifier = CUADClassifier(
    clause_types=["termination_for_cause", "indemnification", "liability_cap"],
    multi_label=True,
    confidence_threshold=0.85
)

classified_clauses = classifier.classify(contract)
print(f"\nClassified {len(classified_clauses)} clauses")

# Custom risk analysis with playbook
analyzer = RiskAnalyzer(
    playbook_path="custom_risk_playbook.json",
    severity_thresholds={
        "critical": 0.9,
        "high": 0.7,
        "medium": 0.5,
        "low": 0.3
    }
)

risks = analyzer.analyze(contract)
critical_risks = [r for r in risks if r.severity == "critical"]

print(f"\nIdentified {len(critical_risks)} critical risks:")
for risk in critical_risks:
    print(f"  - {risk.risk_type}: {risk.description}")
    print(f"    Recommendation: {risk.recommendation}")

# Export with custom formatting
contract.to_json("advanced_output.json", indent=4)
contract.to_excel("advanced_output.xlsx")
