"""
Conflict detection for RAG retrieval results.

The central problem identified in production legal AI systems: when two
retrieved sources give conflicting answers to the same question, a naive
RAG pipeline summarises them into a single answer that presents false
consensus.  This module detects conflicts *before* the LLM generates an
answer so the prompt can explicitly instruct the model to present both
positions.

Conflict types
--------------
JURISDICTION_CONFLICT
    Same legal question, different regional outcomes.  Common in US state
    law and German Bundesland-level regulatory variation.
AUTHORITY_CONFLICT
    A lower court's holding contradicts a higher court on the same issue.
TEMPORAL_CONFLICT
    An older ruling conflicts with a newer ruling — the older may be
    implicitly overruled or the newer may not yet have been widely applied.
UNSETTLED_QUESTION
    Multiple high-authority sources of similar rank disagree.  No clear
    winner — the answer should present the circuit split / open question.

Usage
-----
::

    from contractex.rag.conflict import ConflictDetector

    detector = ConflictDetector()
    conflicts = detector.detect(docs, query="Can an employer terminate for cause?")

    # Conflicts are embedded in the RAG prompt so the LLM surfaces them
    # rather than flattening them.
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from contractex.core.document import LegalDoc

logger = logging.getLogger(__name__)


class ConflictType(str, Enum):
    """Classification of the conflict between two sources."""

    JURISDICTION_CONFLICT = "jurisdiction_conflict"
    """Same question, different regional outcomes."""

    AUTHORITY_CONFLICT = "authority_conflict"
    """Lower court / source contradicts higher-authority source."""

    TEMPORAL_CONFLICT = "temporal_conflict"
    """Older source conflicts with newer source on same issue."""

    UNSETTLED_QUESTION = "unsettled_question"
    """Multiple high-authority sources disagree — no clear winner."""


class Conflict(BaseModel):
    """
    A detected conflict between two or more retrieved sources.

    Attributes
    ----------
    conflict_type:
        Classification of the conflict.
    source_a_id:
        ``doc_id`` of the first conflicting source.
    source_b_id:
        ``doc_id`` of the second conflicting source (may be None for
        multi-source unsettled questions).
    source_a_title:
        Human-readable title for source A.
    source_b_title:
        Human-readable title for source B.
    description:
        One-sentence description of the conflict for the LLM prompt.
    severity:
        ``"high"`` — directly contradictory holdings from binding sources.
        ``"medium"`` — persuasive vs binding, or regional vs federal.
        ``"low"`` — minor variation or different emphasis.
    """

    conflict_type: ConflictType
    source_a_id: str
    source_b_id: str | None = None
    source_a_title: str = ""
    source_b_title: str = ""
    description: str = ""
    severity: str = Field("medium", pattern="^(high|medium|low)$")


class ConflictDetector:
    """
    Scans a list of retrieved ``LegalDoc`` objects for conflicting positions
    before the context window is assembled for the LLM.

    When conflicts are detected, the caller is expected to:
    1. Pass both positions to the LLM with an explicit instruction to
       present both and flag the disagreement.
    2. Populate ``RAGResponse.conflicts`` so downstream consumers can
       surface the conflict to users.
    3. Never allow the LLM prompt to present a false consensus.

    Parameters
    ----------
    authority_conflict_gap:
        Minimum ``AuthorityLevel`` gap between two sources for their
        disagreement to be classified as ``AUTHORITY_CONFLICT`` rather than
        ``UNSETTLED_QUESTION``.  Default: 20 points.
    temporal_conflict_years:
        Minimum year gap between two sources for a disagreement to be
        flagged as ``TEMPORAL_CONFLICT``.  Default: 5 years.
    """

    def __init__(
        self,
        authority_conflict_gap: int = 20,
        temporal_conflict_years: int = 5,
    ) -> None:
        self._authority_gap = authority_conflict_gap
        self._temporal_gap = temporal_conflict_years

    def detect(self, docs: list[LegalDoc], query: str = "") -> list[Conflict]:
        """
        Detect conflicts among *docs*.

        Parameters
        ----------
        docs:
            Retrieved ``LegalDoc`` objects (typically the top-k RAG hits).
        query:
            The user query — used only for logging at this stage.

        Returns
        -------
        list[Conflict]
            Empty list when no conflicts are detected.
        """
        conflicts: list[Conflict] = []
        if len(docs) < 2:
            return conflicts

        for i in range(len(docs)):
            for j in range(i + 1, len(docs)):
                doc_a = docs[i]
                doc_b = docs[j]
                detected = self._compare(doc_a, doc_b)
                conflicts.extend(detected)

        if conflicts:
            logger.info(
                "ConflictDetector: %d conflict(s) detected for query %r",
                len(conflicts),
                query[:80],
            )
        return conflicts

    def build_conflict_prompt_addendum(self, conflicts: list[Conflict]) -> str:
        """
        Return text to append to the RAG prompt when conflicts are present.

        The addendum instructs the LLM to present both positions explicitly
        and never flatten them into a single answer.
        """
        if not conflicts:
            return ""

        lines = [
            "\n\nIMPORTANT — CONFLICTING SOURCES DETECTED:",
            "The retrieved sources contain conflicting positions on this question.",
            "You MUST present BOTH positions clearly and indicate that the law is",
            "unsettled or varies by jurisdiction.  Do NOT present false consensus.",
            "",
            "Conflicts:",
        ]
        for c in conflicts:
            lines.append(
                f"  [{c.conflict_type.value.upper()}] {c.description or 'See sources below.'}"
            )
        lines.append("\nLabel each position with its source [N] and note whether it is binding.")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Internal comparison logic
    # ------------------------------------------------------------------

    def _compare(self, doc_a: LegalDoc, doc_b: LegalDoc) -> list[Conflict]:
        """Compare a pair of documents and return any detected conflicts."""
        results: list[Conflict] = []

        profile_a = doc_a.authority_profile
        profile_b = doc_b.authority_profile

        # --- Jurisdiction conflict ----------------------------------------
        jur_a = doc_a.effective_jurisdiction_tag
        jur_b = doc_b.effective_jurisdiction_tag
        if jur_a is not None and jur_b is not None:
            if jur_a.conflicts_with(jur_b):
                results.append(
                    Conflict(
                        conflict_type=ConflictType.JURISDICTION_CONFLICT,
                        source_a_id=doc_a.doc_id,
                        source_b_id=doc_b.doc_id,
                        source_a_title=self._title(doc_a),
                        source_b_title=self._title(doc_b),
                        description=(
                            f"Source A applies to {jur_a} while Source B applies to {jur_b} "
                            f"— the answer may differ across these jurisdictions."
                        ),
                        severity="high" if self._both_binding(jur_a, jur_b) else "medium",
                    )
                )

        # --- Authority conflict & unsettled question ----------------------
        if profile_a is not None and profile_b is not None:
            level_a = int(getattr(profile_a, "level", 1))
            level_b = int(getattr(profile_b, "level", 1))
            gap = abs(level_a - level_b)

            # Temporal conflict
            year_a = getattr(profile_a, "publication_year", None)
            year_b = getattr(profile_b, "publication_year", None)
            if year_a and year_b and abs(year_a - year_b) >= self._temporal_gap:
                results.append(
                    Conflict(
                        conflict_type=ConflictType.TEMPORAL_CONFLICT,
                        source_a_id=doc_a.doc_id,
                        source_b_id=doc_b.doc_id,
                        source_a_title=self._title(doc_a),
                        source_b_title=self._title(doc_b),
                        description=(
                            f"Source A ({year_a}) and Source B ({year_b}) are separated by "
                            f"{abs(year_a - year_b)} years — verify which reflects current law."
                        ),
                        severity="high" if gap < self._authority_gap else "medium",
                    )
                )

            # Authority conflict (clear hierarchy difference)
            if gap >= self._authority_gap and not results:
                higher, lower = (doc_a, doc_b) if level_a > level_b else (doc_b, doc_a)
                results.append(
                    Conflict(
                        conflict_type=ConflictType.AUTHORITY_CONFLICT,
                        source_a_id=higher.doc_id,
                        source_b_id=lower.doc_id,
                        source_a_title=self._title(higher),
                        source_b_title=self._title(lower),
                        description=(
                            f"Source A ({self._title(higher)}) has higher authority than "
                            f"Source B ({self._title(lower)}).  If they conflict, Source A governs."
                        ),
                        severity="medium",
                    )
                )

        return results

    @staticmethod
    def _title(doc: LegalDoc) -> str:
        title = (
            getattr(doc.metadata, "title", None)
            or getattr(doc.metadata, "filename", None)
            or doc.doc_id[:12]
        )
        return str(title)

    @staticmethod
    def _both_binding(jur_a: Any, jur_b: Any) -> bool:
        return (
            getattr(jur_a, "applicability", "") == "binding"
            and getattr(jur_b, "applicability", "") == "binding"
        )
