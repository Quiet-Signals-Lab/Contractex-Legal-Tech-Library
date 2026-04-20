"""Prompt templates for contract extraction.

Every prompt has a corresponding version constant.  The version map is
available as PROMPT_VERSIONS for recording in extraction results.
"""

from __future__ import annotations

from contractex.prompts.clause_extraction import (
    CLAUSE_CLASSIFICATION_PROMPT_VERSION,
    CLAUSE_EXTRACTION_PROMPT,
    CLAUSE_EXTRACTION_PROMPT_VERSION,
    CONTRACT_INFO_PROMPT_VERSION,
)
from contractex.prompts.financial_extraction import (
    FINANCIAL_EXTRACTION_PROMPT,
    FINANCIAL_EXTRACTION_PROMPT_VERSION,
)
from contractex.prompts.party_extraction import (
    PARTY_EXTRACTION_PROMPT,
    PARTY_EXTRACTION_PROMPT_VERSION,
)
from contractex.prompts.risk_analysis import RISK_ANALYSIS_PROMPT, RISK_ANALYSIS_PROMPT_VERSION

# Canonical version map — record this in every ExtractionMetadata
PROMPT_VERSIONS: dict[str, str] = {
    "clause_extraction": CLAUSE_EXTRACTION_PROMPT_VERSION,
    "contract_info": CONTRACT_INFO_PROMPT_VERSION,
    "clause_classification": CLAUSE_CLASSIFICATION_PROMPT_VERSION,
    "financial_extraction": FINANCIAL_EXTRACTION_PROMPT_VERSION,
    "party_extraction": PARTY_EXTRACTION_PROMPT_VERSION,
    "risk_analysis": RISK_ANALYSIS_PROMPT_VERSION,
}

__all__ = [
    "CLAUSE_EXTRACTION_PROMPT",
    "CLAUSE_EXTRACTION_PROMPT_VERSION",
    "CONTRACT_INFO_PROMPT_VERSION",
    "CLAUSE_CLASSIFICATION_PROMPT_VERSION",
    "PARTY_EXTRACTION_PROMPT",
    "PARTY_EXTRACTION_PROMPT_VERSION",
    "FINANCIAL_EXTRACTION_PROMPT",
    "FINANCIAL_EXTRACTION_PROMPT_VERSION",
    "RISK_ANALYSIS_PROMPT",
    "RISK_ANALYSIS_PROMPT_VERSION",
    "PROMPT_VERSIONS",
]
