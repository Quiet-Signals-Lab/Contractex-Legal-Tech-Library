"""Prompt templates for contract extraction."""

from __future__ import annotations

from contractex.prompts.clause_extraction import CLAUSE_EXTRACTION_PROMPT
from contractex.prompts.financial_extraction import FINANCIAL_EXTRACTION_PROMPT
from contractex.prompts.party_extraction import PARTY_EXTRACTION_PROMPT
from contractex.prompts.risk_analysis import RISK_ANALYSIS_PROMPT

__all__ = [
    "CLAUSE_EXTRACTION_PROMPT",
    "PARTY_EXTRACTION_PROMPT",
    "FINANCIAL_EXTRACTION_PROMPT",
    "RISK_ANALYSIS_PROMPT",
]
