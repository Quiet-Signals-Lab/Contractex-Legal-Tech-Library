"""
Authority taxonomy for legal source ranking.

Every legal document ingested into ContractEx carries an ``AuthorityProfile``
that describes how authoritative its content is relative to other sources.
The ``LegalRAGPipeline`` uses this profile to weight retrieval scores so that
a Supreme Court ruling outranks a law-review article even when the article's
embedding is a slightly closer match to the query.

Scoring formula (configurable at pipeline construction time)::

    final_score = α * semantic_similarity
                + β * authority_weight        (normalised to [0, 1])
                + γ * recency_weight          (normalised to [0, 1])

Default weights: α=0.60, β=0.30, γ=0.10.

Design rationale
----------------
* ``AuthorityLevel`` uses ``IntEnum`` so numeric comparisons are natural
  (``SUPREME_COURT > TRIAL_COURT``).
* ``is_superseded`` prevents an overruled ruling from being presented as
  current law.  The pipeline filters superseded documents from the primary
  answer context (they may still be shown as "note: this was overruled by…").
* Authority weight normalisation maps the [1, 100] scale to [0.0, 1.0]
  for clean arithmetic with cosine similarity scores.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Any

from pydantic import BaseModel, Field

from contractex.taxonomy.jurisdiction import JurisdictionTag


class AuthorityLevel(IntEnum):
    """
    Ordinal authority weights for legal source types.

    Higher values indicate greater authority.  These values are used as a
    multiplier in retrieval ranking alongside vector similarity.

    Notes
    -----
    * ``REGULATION`` (85) sits above ``APPELLATE_COURT`` (75) because primary
      legislation that has been implemented as regulation is binding in most
      common-law jurisdictions.  This can be overridden per deployment.
    * ``BINDING_TREATY`` (88) is placed between ``REGULATION`` and
      ``SUPREME_COURT`` — binding under international law but may require
      domestic implementing legislation.
    * ``AGENCY_GUIDANCE`` (55) is non-binding but carries more weight than
      secondary literature.
    """

    CONSTITUTIONAL = 100
    BINDING_STATUTE = 95
    BINDING_TREATY = 88
    REGULATION = 85
    SUPREME_COURT = 90
    APPELLATE_COURT = 75
    TRIAL_COURT = 60
    AGENCY_GUIDANCE = 55
    SECONDARY_TREATISE = 30
    LAW_REVIEW = 25
    BAR_ASSOCIATION = 20
    BLOG_NEWS = 5
    UNKNOWN = 1

    @property
    def normalised(self) -> float:
        """Map [1, 100] to [0.01, 1.00] for use in weighted scoring."""
        return self.value / 100.0

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").title()

    def is_binding(self) -> bool:
        """Return True if this level represents a binding legal source."""
        return self.value >= AuthorityLevel.AGENCY_GUIDANCE


class AuthorityProfile(BaseModel):
    """
    Authority metadata attached to every ``LegalDoc``.

    Attributes
    ----------
    level:
        The ``AuthorityLevel`` ordinal for this source.
    jurisdiction:
        Structured jurisdiction tag (country / region / court system).
    court_name:
        Specific court or issuing body (e.g. ``"9th Circuit Court of Appeals"``).
    is_binding:
        True when this source creates binding obligations (as opposed to
        persuasive authority).  Derived automatically from ``level`` if not
        supplied.
    is_superseded:
        True when this ruling or statute has been overruled, repealed, or
        amended to the point of irrelevance.  Superseded documents are
        excluded from primary RAG context but retained for historical queries.
    superseded_by:
        Citation string of the source that superseded this one.
    publication_year:
        Year of publication / decision.  Used for recency weighting.
    """

    level: AuthorityLevel = Field(
        AuthorityLevel.UNKNOWN,
        description="Ordinal authority weight (higher = more authoritative)",
    )
    jurisdiction: JurisdictionTag | None = Field(
        None,
        description="Structured jurisdiction tag for this source",
    )
    court_name: str | None = Field(
        None,
        description="Specific court or issuing body",
    )
    is_binding: bool = Field(
        False,
        description="True when this source creates binding obligations",
    )
    is_superseded: bool = Field(
        False,
        description="True when this ruling or statute has been overruled/repealed",
    )
    superseded_by: str | None = Field(
        None,
        description="Citation of the source that superseded this one",
    )
    publication_year: int | None = Field(
        None,
        description="Year of publication or decision for recency weighting",
    )

    def model_post_init(self, __context: Any) -> None:
        """Derive ``is_binding`` from ``level`` when not explicitly set."""
        if not self.is_binding:
            object.__setattr__(self, "is_binding", self.level.is_binding())

    @property
    def authority_weight(self) -> float:
        """Normalised authority weight [0.01, 1.00]."""
        if self.is_superseded:
            # Superseded sources get a fraction of their original weight so
            # they can still surface for historical queries but never dominate.
            return self.level.normalised * 0.1
        return self.level.normalised

    @classmethod
    def for_level(
        cls,
        level: AuthorityLevel | str | int,
        *,
        jurisdiction: JurisdictionTag | None = None,
        court_name: str | None = None,
        publication_year: int | None = None,
    ) -> AuthorityProfile:
        """Convenience constructor — creates a profile for a given authority level."""
        if isinstance(level, (str, int)):
            level = AuthorityLevel(int(level))
        return cls(
            level=level,
            jurisdiction=jurisdiction,
            court_name=court_name,
            is_binding=level.is_binding(),
            publication_year=publication_year,
        )
