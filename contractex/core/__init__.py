"""Core module initialization."""

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
    # Contract models
    "Contract",
    "Party",
    "Clause",
    "FinancialTerm",
    "RiskFlag",
    "ContractMetadata",
    # General legal document models
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
