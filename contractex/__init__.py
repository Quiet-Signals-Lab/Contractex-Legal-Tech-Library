"""
ContractEx: Modern Contract Intelligence for Python

A comprehensive library for LLM-powered contract analysis and legal document intelligence.
"""

from __future__ import annotations

from contractex.__version__ import __version__
from contractex.core.analyzers import RiskAnalyzer
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
from contractex.utils.audit import AuditLogger
from contractex.utils.provenance import ProvenanceTracker
from contractex.utils.routing import ConfidenceRouter

# New architectural components (lazy-imported to avoid hard deps)
def _lazy(module: str, attr: str):
    """Return a lazy accessor to avoid importing optional deps at package load time."""
    import importlib
    return getattr(importlib.import_module(module), attr)

try:
    from contractex.privacy.profile import PrivacyProfile
except ImportError:  # presidio not installed
    PrivacyProfile = None  # type: ignore[assignment,misc]

try:
    from contractex.tasks.registry import TaskRegistry
except ImportError:
    TaskRegistry = None  # type: ignore[assignment,misc]

try:
    from contractex.rag.pipeline import LegalRAGPipeline
except ImportError:
    LegalRAGPipeline = None  # type: ignore[assignment,misc]


# Simple API for 80% use case
def extract_contract(
    document_path: str,
    llm: str = "gpt-4o",
    confidence_threshold: float = 0.7,
    analyze_risks: bool = True,
    extract_financial: bool = True,
) -> Contract:
    """
    Extract contract data from a document with a simple one-line API.

    Args:
        document_path: Path to the contract document (PDF, DOCX, etc.)
        llm: LLM provider to use ("gpt-4o", "claude-3.5-sonnet", "llama-3.1-70b")
        confidence_threshold: Minimum confidence score for extractions (0.0-1.0)
        analyze_risks: Whether to perform risk analysis
        extract_financial: Whether to extract financial terms

    Returns:
        Contract: Extracted contract data with parties, clauses, risks, etc.

    Example:
        >>> contract = extract_contract("contract.pdf")
        >>> print(contract.parties)
        >>> print(contract.clauses)
        >>> print(contract.risks)
    """
    extractor = ContractExtractor(
        llm_provider_name=llm,
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
    # Contract models
    "Contract",
    "Party",
    "Clause",
    "FinancialTerm",
    "RiskFlag",
    "ContractMetadata",
    "ContractExtractor",
    "CUADClassifier",
    "RiskAnalyzer",
    # General legal document models
    "LegalDocument",
    "LegalDocumentMetadata",
    "DocType",
    "SourceSpan",
    # Pipeline utilities
    "ProvenanceTracker",
    "ConfidenceRouter",
    "AuditLogger",
]

# Optional modules (require additional dependencies):
# - contractex.storage:   PostgreSQL persistence     pip install contractex[storage]
# - contractex.data:      Dataset loaders            pip install contractex[datasets]
# - contractex.core.ner:  Named Entity Recognition   pip install contractex[spacy]
# - contractex.retrieval: Search and ranking         pip install contractex[retrieval]
# - contractex.loaders.source_adapter: URL/API loaders  pip install contractex[network]
# - contractex.eval:      Eval harness               pip install contractex[eval]
