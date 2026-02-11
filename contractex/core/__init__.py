"""Core module initialization."""

from contractex.core.models import (
    Contract,
    Party,
    Clause,
    FinancialTerm,
    RiskFlag,
    ContractMetadata,
)

# Optional NER support (requires spacy)
try:
    from contractex.core.ner import LegalNER
    __all__ = [
        "Contract",
        "Party",
        "Clause",
        "FinancialTerm",
        "RiskFlag",
        "ContractMetadata",
        "LegalNER",
    ]
except ImportError:
    # spacy not installed
    __all__ = [
        "Contract",
        "Party",
        "Clause",
        "FinancialTerm",
        "RiskFlag",
        "ContractMetadata",
    ]

