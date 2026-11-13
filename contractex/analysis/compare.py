"""
Contract version comparison — Layer 3.

Compare two extraction results (or two lists of clauses) to identify
what changed between contract versions: added, removed, and modified clauses.

Zero LLM calls.  Uses text similarity for modified-clause detection.

Usage::

    from contractex.analysis import compare

    diff = compare(result_v1, result_v2)
    print(diff.added_clauses)     # clause types new in v2
    print(diff.removed_clauses)   # clause types removed from v2
    print(diff.modified_clauses)  # same type, changed text (edited, added or removed)
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


@dataclass
class ClauseChange:
    """
    A change to a clause whose type exists in both versions.

    An edited clause carries both texts.  A clause with no counterpart in the
    other version has ``text_v2 == ""`` (removed) or ``text_v1 == ""`` (added),
    and similarity 0.0.
    """

    clause_type: str
    section_ref_v1: str
    section_ref_v2: str
    text_v1: str
    text_v2: str
    similarity: float  # 0.0–1.0; 1.0 = identical


@dataclass
class ContractDiff:
    """The result of comparing two contract extraction results."""

    added_clauses: list[str] = field(default_factory=list)  # clause types in v2, not v1
    removed_clauses: list[str] = field(default_factory=list)  # clause types in v1, not v2
    modified_clauses: list[ClauseChange] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Added:    {len(self.added_clauses)} clause type(s)",
            f"Removed:  {len(self.removed_clauses)} clause type(s)",
            f"Modified: {len(self.modified_clauses)} clause(s)",
        ]
        if self.added_clauses:
            lines.append(f"  + {', '.join(self.added_clauses)}")
        if self.removed_clauses:
            lines.append(f"  - {', '.join(self.removed_clauses)}")
        for mc in self.modified_clauses:
            what = (
                "added"
                if not mc.text_v1
                else "removed" if not mc.text_v2 else f"similarity={mc.similarity:.2f}"
            )
            lines.append(f"  ~ {mc.clause_type} ({what})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _get_clauses(result: object) -> list:
    """Extract clauses from whatever result type is passed in."""
    if hasattr(result, "clauses"):
        return list(result.clauses)  # type: ignore[return-value]
    if isinstance(result, list):
        return result
    return []


def _clause_type(c: object) -> str:
    if hasattr(c, "clause_type"):
        return str(c.clause_type)  # type: ignore[return-value]
    if isinstance(c, dict):
        return str(c.get("clause_type", ""))
    return ""


def _clause_text(c: object) -> str:
    if hasattr(c, "text"):
        return str(c.text)  # type: ignore[return-value]
    if isinstance(c, dict):
        return str(c.get("text", ""))
    return ""


def _clause_ref(c: object) -> str:
    for attr in ("section_number", "section_ref", "id"):
        if hasattr(c, attr):
            val = getattr(c, attr)
            if val:
                return str(val)
    return ""


# ---------------------------------------------------------------------------
# compare()
# ---------------------------------------------------------------------------


def compare(
    result_v1: object,
    result_v2: object,
    similarity_threshold: float = 0.85,
) -> ContractDiff:
    """
    Compare two contract extraction results.

    Args:
        result_v1: First extraction result (or list of clauses).
        result_v2: Second extraction result (or list of clauses).
        similarity_threshold: Clauses of the same type with text similarity at
            or above this value are considered "same clause, minor edit" and
            reported as one ClauseChange; below it they are reported as one
            removed and one added ClauseChange.  Default 0.85.

    Returns:
        ContractDiff with added and removed clause types, and every changed
        clause of a type present in both versions.
    """
    clauses_v1 = _get_clauses(result_v1)
    clauses_v2 = _get_clauses(result_v2)

    # Build maps: clause_type → list of clauses
    map_v1: dict[str, list] = {}
    for c in clauses_v1:
        map_v1.setdefault(_clause_type(c), []).append(c)

    map_v2: dict[str, list] = {}
    for c in clauses_v2:
        map_v2.setdefault(_clause_type(c), []).append(c)

    types_v1 = set(map_v1.keys())
    types_v2 = set(map_v2.keys())

    added_types = types_v2 - types_v1
    removed_types = types_v1 - types_v2
    common_types = types_v1 & types_v2

    modified: list[ClauseChange] = []

    for ct in sorted(common_types):
        matched_v2: set[int] = set()  # indices into map_v2[ct] that have a v1 counterpart

        for c1 in map_v1[ct]:
            text1 = _clause_text(c1)
            best_sim = -1.0
            best_idx = 0

            for idx, c2 in enumerate(map_v2[ct]):
                sim = difflib.SequenceMatcher(None, text1, _clause_text(c2)).ratio()
                if sim > best_sim:
                    best_sim = sim
                    best_idx = idx

            if best_sim >= similarity_threshold:
                matched_v2.add(best_idx)
                if best_sim < 1.0:
                    # Substantially the same, small edit
                    best_c2 = map_v2[ct][best_idx]
                    modified.append(
                        ClauseChange(
                            clause_type=ct,
                            section_ref_v1=_clause_ref(c1),
                            section_ref_v2=_clause_ref(best_c2),
                            text_v1=text1,
                            text_v2=_clause_text(best_c2),
                            similarity=best_sim,
                        )
                    )
            else:
                # Nothing close enough in v2: removed (or rewritten beyond recognition)
                modified.append(ClauseChange(ct, _clause_ref(c1), "", text1, "", 0.0))

        for idx, c2 in enumerate(map_v2[ct]):
            if idx not in matched_v2:
                # No v1 clause maps to it: added (or the rewrite of a removed one)
                modified.append(ClauseChange(ct, "", _clause_ref(c2), "", _clause_text(c2), 0.0))

    return ContractDiff(
        added_clauses=sorted(added_types),
        removed_clauses=sorted(removed_types),
        modified_clauses=modified,
    )
