"""Core module initialization."""

from __future__ import annotations

from contractex.core.document import LegalDoc, LegalDocMetadata  # noqa: F401
from contractex.core.legal_document import (  # noqa: F401
    DocType,
    LegalDocument,
    LegalDocumentMetadata,
    SourceSpan,
)
from contractex.core.models import (  # noqa: F401
    Clause,
    Contract,
    ContractMetadata,
    FinancialTerm,
    Party,
    RiskFlag,
)

_BASE_ALL = [
    # Unified base model
    "LegalDoc",
    "LegalDocMetadata",
    # Contract models
    "Contract",
    "Party",
    "Clause",
    "FinancialTerm",
    "RiskFlag",
    "ContractMetadata",
    # General legal document models (legacy — use LegalDoc going forward)
    "LegalDocument",
    "LegalDocumentMetadata",
    "DocType",
    "SourceSpan",
]

# Optional NER support (requires spacy)
try:
    from contractex.core.ner import LegalNER

    __all__ = _BASE_ALL + ["LegalNER"]
except ImportError:
    __all__ = _BASE_ALL
