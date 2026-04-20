"""
Structured jurisdiction model for legal documents.

Replaces the flat ``jurisdiction: str`` field on ``LegalDoc`` with a
queryable hierarchy that the RAG pipeline can filter and weight on.

Design notes
------------
* ``country`` uses ISO 3166-1 alpha-2 codes (``"US"``, ``"DE"``, ``"GB"``).
* ``region`` holds the state / province / Bundesland (``"CA"``, ``"BY"``).
* ``court_system`` distinguishes the type of legal authority — ``"federal"``,
  ``"state"``, ``"administrative"``, ``"international"`` etc.
* ``applicability`` classifies whether the source is binding in the target
  jurisdiction, merely persuasive, or informational only.

Hierarchy rules
---------------
Federal supersedes state; national supersedes regional.  Two sources
conflict when they share the same country and domain but differ in region
(e.g. California and Texas insurance regulations answering the same question).

Utility methods
---------------
* ``is_broader_than`` — True when ``self`` has wider geographic scope.
* ``conflicts_with``  — True when two tags describe the same domain but
  different sub-jurisdictions (signal for ConflictDetector).
* ``matches``         — True when a filter tag is compatible with this tag
  (used for hard jurisdiction filtering in RAG query).
* ``from_string``     — Parse a legacy flat string like ``"US-CA"`` or
  ``"DE-BY"``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class JurisdictionTag(BaseModel):
    """
    Structured representation of a legal jurisdiction.

    Attributes
    ----------
    country:
        ISO 3166-1 alpha-2 country code (e.g. ``"US"``, ``"DE"``, ``"GB"``).
        Use ``"INT"`` for international / supranational sources.
    region:
        State, province, or Bundesland code (e.g. ``"CA"``, ``"BY"``).
        ``None`` means the source applies nationally / federally.
    court_system:
        Type of authority: ``"federal"``, ``"state"``, ``"administrative"``,
        ``"international"``, or ``"other"``.
    applicability:
        ``"binding"`` — creates binding obligations.
        ``"persuasive"`` — treated as persuasive (e.g. foreign case cited
        for reasoning).
        ``"informational"`` — background or educational only.
    """

    country: str = Field(
        ...,
        min_length=2,
        max_length=3,
        description="ISO 3166-1 alpha-2 country code, or 'INT' for international",
    )
    region: str | None = Field(
        None,
        description="State / province / Bundesland code.  None = national scope.",
    )
    court_system: str | None = Field(
        None,
        description="federal | state | administrative | international | other",
    )
    applicability: Literal["binding", "persuasive", "informational"] = Field(
        "binding",
        description="Whether this source is binding, persuasive, or informational",
    )

    @model_validator(mode="after")
    def _normalise(self) -> "JurisdictionTag":
        object.__setattr__(self, "country", self.country.upper())
        if self.region:
            object.__setattr__(self, "region", self.region.upper())
        return self

    # ------------------------------------------------------------------
    # Hierarchy reasoning
    # ------------------------------------------------------------------

    def is_broader_than(self, other: "JurisdictionTag") -> bool:
        """
        Return True when *self* has wider geographic scope than *other*.

        Rules
        -----
        * Same country, self has no region, other has a region → self is broader.
        * International (``country="INT"``) is broader than any national source.
        * Different countries → not comparable (returns False).
        """
        if self.country == "INT" and other.country != "INT":
            return True
        if self.country != other.country:
            return False
        # Same country: federal (no region) is broader than state
        return self.region is None and other.region is not None

    def conflicts_with(self, other: "JurisdictionTag") -> bool:
        """
        Return True when the two tags describe the same country but different
        regions — a signal that the sources may give conflicting answers.

        Intended for use by ``ConflictDetector``.
        """
        if self.country != other.country:
            return False
        # Different defined regions in the same country
        if self.region and other.region and self.region != other.region:
            return True
        return False

    def matches(self, query_filter: "JurisdictionTag") -> bool:
        """
        Return True when *self* is compatible with *query_filter*.

        Compatibility rules (used for hard filtering in RAG query)
        ---------------------------------------------------------
        * Country must match (or filter country is ``"INT"`` — matches all).
        * If the filter specifies a region, self must match that region
          **or** have no region (federal/national sources match any state query).
        * Applicability must be ``"binding"`` when the filter is ``"binding"``.
        """
        if query_filter.country != "INT" and self.country != query_filter.country:
            return False
        if query_filter.region is not None:
            if self.region is not None and self.region != query_filter.region:
                return False
        if query_filter.applicability == "binding" and self.applicability != "binding":
            return False
        return True

    # ------------------------------------------------------------------
    # Parsers / constructors
    # ------------------------------------------------------------------

    @classmethod
    def from_string(cls, s: str) -> "JurisdictionTag":
        """
        Parse a legacy flat jurisdiction string.

        Supported formats::

            "US"          → country=US, region=None
            "US-Federal"  → country=US, court_system=federal, region=None
            "US-CA"       → country=US, region=CA
            "DE-BY"       → country=DE, region=BY
            "EU"          → country=INT (EU treated as international)
        """
        s = s.strip()
        if s.upper() in ("EU", "INT", "INTERNATIONAL"):
            return cls(country="INT", applicability="binding")

        parts = s.split("-", 1)
        country = parts[0].upper()

        if len(parts) == 1:
            return cls(country=country, applicability="binding")

        suffix = parts[1].upper()
        if suffix in ("FEDERAL", "FED"):
            return cls(country=country, court_system="federal", applicability="binding")
        # Otherwise treat suffix as a region code
        return cls(country=country, region=suffix, applicability="binding")

    def __str__(self) -> str:
        if self.region:
            return f"{self.country}-{self.region}"
        if self.court_system:
            return f"{self.country}-{self.court_system.title()}"
        return self.country
