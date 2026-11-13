"""
Contractex: A Python library for building contract analysis pipelines.

Architecture (four layers):

    LAYER 3 · ANALYSIS          Risk · Obligations · Comparison
    LAYER 2 · EXTRACTION        LLM (scoped, schema-constrained)
    LAYER 1 · STRUCTURAL PARSE  Deterministic, fully testable
    LAYER 0 · INGEST            Format-specific loaders

Layer 1 has zero LLM calls.  Every structural decision is deterministic
and auditable — which matters enormously in the legal context.

Quick start::

    # Full pipeline
    from contractex import ContractExtractor
    from contractex.structure import parse_structure
    from contractex.analysis import RiskAnalyzer
    from contractex.playbooks import StandardNDAPlaybook

    # Layer 1: deterministic structural parse (no LLM)
    structure = parse_structure(open("nda.txt").read())

    # Layer 2: schema-constrained LLM extraction
    extractor = ContractExtractor(llm_provider_name="llama3.1:8b")
    result = extractor.extract("nda.pdf")

    # Layer 3: playbook-based analysis (no LLM)
    analyzer = RiskAnalyzer(playbook=StandardNDAPlaybook())
    risks = analyzer.analyze(result)
    gaps = analyzer.missing_clauses(result)

    # Prompt version provenance
    print(result.metadata.prompt_versions)

Privacy-first: the full pipeline runs locally with Llama 3.1.
Measured on CUAD: see ``benchmarks/`` in the repository.
"""

from __future__ import annotations

import logging

from contractex.__version__ import __version__

# Layer 3: analysis (no LLM)
from contractex.analysis import (
    ObligationTimeline,
    PlaybookFlag,
    RiskAnalyzer,
)
from contractex.analysis import (
    compare as compare_contracts,
)

# Layer 2: extraction
from contractex.core.classifiers import CUADClassifier
from contractex.core.document import LegalDoc, LegalDocMetadata
from contractex.core.extractors import ContractExtractor
from contractex.core.legal_document import DocType, LegalDocument, LegalDocumentMetadata, SourceSpan
from contractex.core.models import (
    Clause,
    Contract,
    ContractMetadata,
    FinancialTerm,
    Party,
    RiskFlag,
)

# Eval
from contractex.eval import CalibrationAnalyzer, CUADBenchmark
from contractex.exceptions import (
    ContractExError,
    DocumentLoadError,
    ExtractionError,
    LLMProviderError,
)
from contractex.llm.base import LLMProvider

# Playbooks
from contractex.playbooks import (
    Playbook,
    SaaSPlaybook,
    StandardNDAPlaybook,
)
from contractex.privacy.profile import PrivacyProfile
from contractex.rag.pipeline import LegalRAGPipeline

# Layer 1: structural parse (deterministic, no LLM)
from contractex.structure import (
    DefinedTerm,
    DocumentStructure,
    Section,
    parse_structure,
)
from contractex.tasks.registry import TaskRegistry
from contractex.utils.audit import AuditLogger
from contractex.utils.provenance import ProvenanceTracker
from contractex.utils.routing import ConfidenceRouter

# A library must not print log records unless the application asks for them.
logging.getLogger(__name__).addHandler(logging.NullHandler())


# Simple API for 80% use case
def extract_contract(
    document_path: str,
    llm: str | LLMProvider,
    confidence_threshold: float = 0.7,
    analyze_risks: bool = True,
    extract_financial: bool = True,
) -> Contract:
    """
    Extract contract data from a document with a simple one-line API.

    Args:
        document_path: Path to the contract document (PDF, DOCX, etc.)
        llm: An LLMProvider instance, or a full model name (``gpt-...``,
            ``claude-...``, or an Ollama model such as ``llama3.1:8b``).
            Required: the library has no default provider.
        confidence_threshold: Minimum confidence score for extractions (0.0-1.0)
        analyze_risks: Whether to perform risk analysis
        extract_financial: Whether to extract financial terms

    Returns:
        Contract: Extracted contract data with parties, clauses, risks, etc.

    Example:
        >>> contract = extract_contract("contract.pdf", llm="llama3.1:8b")
        >>> print(contract.parties)
        >>> print(contract.clauses)
        >>> print(contract.risks)
    """
    extractor = ContractExtractor(
        llm_provider=llm if not isinstance(llm, str) else None,
        llm_provider_name=llm if isinstance(llm, str) else None,
        confidence_threshold=confidence_threshold,
    )

    contract = extractor.extract(
        document_path,
        analyze_risks=analyze_risks,
        extract_financial=extract_financial,
    )

    return contract


__all__ = [
    "__version__",
    "extract_contract",
    # Layer 1: structural parse
    "parse_structure",
    "DocumentStructure",
    "Section",
    "DefinedTerm",
    # Layer 2: extraction
    "ContractExtractor",
    "CUADClassifier",
    "Contract",
    "Party",
    "Clause",
    "FinancialTerm",
    "RiskFlag",
    "ContractMetadata",
    # Layer 3: analysis
    "RiskAnalyzer",
    "PlaybookFlag",
    "ObligationTimeline",
    "compare_contracts",
    # Playbooks
    "Playbook",
    "StandardNDAPlaybook",
    "SaaSPlaybook",
    # Eval
    "CUADBenchmark",
    "CalibrationAnalyzer",
    # General legal document models
    "LegalDocument",
    "LegalDocumentMetadata",
    "DocType",
    "SourceSpan",
    "LegalDoc",
    "LegalDocMetadata",
    # Pipeline utilities
    "ProvenanceTracker",
    "ConfidenceRouter",
    "AuditLogger",
    # Privacy, tasks and retrieval
    "PrivacyProfile",
    "TaskRegistry",
    "LegalRAGPipeline",
    # Providers and errors
    "LLMProvider",
    "ContractExError",
    "DocumentLoadError",
    "ExtractionError",
    "LLMProviderError",
]

# Optional modules (require additional dependencies):
# - contractex.storage:   PostgreSQL persistence     pip install contractex[storage]
# - contractex.core.ner:  Named Entity Recognition   pip install contractex[spacy]
# - contractex.rag:       RAG pipeline               pip install contractex[rag]
# - LLM providers:        openai / anthropic / google / ollama extras
