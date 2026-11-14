"""Taxonomy definitions for clause classification and legal authority."""

from __future__ import annotations

from contractex.taxonomy.authority import AuthorityLevel, AuthorityProfile
from contractex.taxonomy.cuad import CUADClauseType
from contractex.taxonomy.jurisdiction import JurisdictionTag

__all__ = [
    "CUADClauseType",
    "JurisdictionTag",
    "AuthorityLevel",
    "AuthorityProfile",
]
