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
    print(diff.modified_clauses)  # same type, changed text
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Output types
# ---------------------------------------------------------------------------


@dataclass
class ClauseChange:
    """A clause that exists in both versions but with different text."""

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
            lines.append(f"  ~ {mc.clause_type} (similarity={mc.similarity:.2f})")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Extraction helpers
# ---------------------------------------------------------------------------


def _get_clauses(result: object) -> list:
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
        similarity_threshold: Clauses with text similarity above this value
            are considered "same clause, minor edit" rather than "removed + added".
            Default 0.85.

    Returns:
        ContractDiff with added, removed, and modified clauses.
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

    for ct in common_types:
        for c1 in map_v1[ct]:
            text1 = _clause_text(c1)
            best_sim = 0.0
            best_c2 = None

            for c2 in map_v2[ct]:
                text2 = _clause_text(c2)
                sim = difflib.SequenceMatcher(None, text1, text2).ratio()
                if sim > best_sim:
                    best_sim = sim
                    best_c2 = c2

            # If best match is not identical, record as modified
            if best_c2 is not None and best_sim < 1.0:
                if best_sim >= similarity_threshold:
                    # Substantially the same, small edit
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

    return ContractDiff(
        added_clauses=sorted(added_types),
        removed_clauses=sorted(removed_types),
        modified_clauses=modified,
    )
