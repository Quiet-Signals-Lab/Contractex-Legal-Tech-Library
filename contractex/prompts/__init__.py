"""Prompt templates for contract extraction.

Every prompt has a corresponding version constant.  The version map is
available as PROMPT_VERSIONS for recording in extraction results.
"""

from __future__ import annotations

from contractex.prompts.clause_extraction import (
    CLAUSE_EXTRACTION_PROMPT,
    CLAUSE_EXTRACTION_PROMPT_VERSION,
    CONTRACT_INFO_PROMPT_VERSION,
)
from contractex.prompts.financial_extraction import (
    FINANCIAL_EXTRACTION_PROMPT,
    FINANCIAL_EXTRACTION_PROMPT_VERSION,
)
from contractex.prompts.risk_analysis import RISK_ANALYSIS_PROMPT, RISK_ANALYSIS_PROMPT_VERSION

# Version of every prompt the library sends; a Contract records the ones it used
PROMPT_VERSIONS: dict[str, str] = {
    "clause_extraction": CLAUSE_EXTRACTION_PROMPT_VERSION,
    "contract_info": CONTRACT_INFO_PROMPT_VERSION,
    "financial_extraction": FINANCIAL_EXTRACTION_PROMPT_VERSION,
    "risk_analysis": RISK_ANALYSIS_PROMPT_VERSION,
}

__all__ = [
    "CLAUSE_EXTRACTION_PROMPT",
    "CLAUSE_EXTRACTION_PROMPT_VERSION",
    "CONTRACT_INFO_PROMPT_VERSION",
    "FINANCIAL_EXTRACTION_PROMPT",
    "FINANCIAL_EXTRACTION_PROMPT_VERSION",
    "RISK_ANALYSIS_PROMPT",
    "RISK_ANALYSIS_PROMPT_VERSION",
    "PROMPT_VERSIONS",
]
