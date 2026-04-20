"""Taxonomy definitions for clause classification and legal authority."""

from __future__ import annotations

from contractex.taxonomy.authority import AuthorityLevel, AuthorityProfile
from contractex.taxonomy.cuad import CUADClauseType
from contractex.taxonomy.jurisdiction import JurisdictionTag
from contractex.taxonomy.schemas import ClauseTypeSchema

__all__ = [
    "CUADClauseType",
    "ClauseTypeSchema",
    "JurisdictionTag",
    "AuthorityLevel",
    "AuthorityProfile",
]
