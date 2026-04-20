"""
Playbook-based risk analysis — Layer 3.

RiskAnalyzer takes an extraction result (or a list of clauses) and a
Playbook, evaluates every rule deterministically, and returns a list of
RiskFlag objects.

No LLM calls.  All decisions are rule-based and auditable.

Usage::

    from contractex.analysis import RiskAnalyzer
    from contractex.playbooks import StandardNDAPlaybook

    analyzer = RiskAnalyzer(playbook=StandardNDAPlaybook())
    risks = analyzer.analyze(extraction_result)
    gaps = analyzer.missing_clauses(extraction_result)
"""

from __future__ import annotations

from dataclasses import dataclass

from contractex.playbooks.base import Playbook, RiskSeverity

# ---------------------------------------------------------------------------
# Analysis output types (separate from core models to keep the analysis
# module self-contained and importable without heavy core dependencies)
# ---------------------------------------------------------------------------


@dataclass
class RiskFlag:
    """A risk identified by a playbook rule."""

    clause_ref: str  # e.g. "8.1" or "" if missing-clause check
    severity: RiskSeverity
    description: str
    playbook_rule: str  # rule id, e.g. "nda.indemnification.must_be_bilateral"
    recommended_language: str = ""
    clause_text: str = ""  # the clause text that triggered the flag


# ---------------------------------------------------------------------------
# Extraction result protocol
# ---------------------------------------------------------------------------
# We use a structural typing approach so the analyzer works with both the
# legacy Contract model and any future extraction result type.


class _HasClauses:
    """Protocol: any object with a .clauses attribute (list of Clause-like)."""


def _get_clauses(result: object) -> list:
    """Extract clauses from whatever result type is passed in."""
    if hasattr(result, "clauses"):
        return list(result.clauses)  # type: ignore[return-value]
    if isinstance(result, list):
        return result
    return []


def _clause_type(clause: object) -> str:
    if hasattr(clause, "clause_type"):
        return str(clause.clause_type)  # type: ignore[return-value]
    if isinstance(clause, dict):
        return str(clause.get("clause_type", ""))
    return ""


def _clause_text(clause: object) -> str:
    if hasattr(clause, "text"):
        return str(clause.text)  # type: ignore[return-value]
    if isinstance(clause, dict):
        return str(clause.get("text", ""))
    return ""


def _clause_ref(clause: object) -> str:
    for attr in ("section_number", "section_ref", "id"):
        if hasattr(clause, attr):
            val = getattr(clause, attr)
            if val:
                return str(val)
    return ""


# ---------------------------------------------------------------------------
# Risk analyzer
# ---------------------------------------------------------------------------


class RiskAnalyzer:
    """
    Evaluate a Playbook against an extraction result.

    Args:
        playbook: A Playbook instance (NDA, SaaS, or custom YAML-loaded).
    """

    def __init__(self, playbook: Playbook) -> None:
        self.playbook = playbook

    def analyze(self, result: object) -> list[RiskFlag]:
        """
        Run all playbook rules against *result* and return a list of RiskFlags.

        Args:
            result: Any object with a .clauses attribute (Contract, ExtractionResult,
                    or a list of Clause objects).

        Returns:
            list[RiskFlag] — one entry per rule that fired.
        """
        clauses = _get_clauses(result)
        clause_types_present: set[str] = {_clause_type(c) for c in clauses}
        flags: list[RiskFlag] = []

        for rule in self.playbook.rules:
            # Missing-clause check
            if rule.flag_if_missing and rule.clause_type not in clause_types_present:
                flags.append(
                    RiskFlag(
                        clause_ref="",
                        severity=rule.severity,
                        description=rule.description,
                        playbook_rule=rule.id,
                        recommended_language=rule.recommended_language,
                        clause_text="",
                    )
                )
                continue

            # Per-clause evaluation
            for clause in clauses:
                if _clause_type(clause) != rule.clause_type:
                    continue
                text = _clause_text(clause)
                if rule.matches(text):
                    flags.append(
                        RiskFlag(
                            clause_ref=_clause_ref(clause),
                            severity=rule.severity,
                            description=rule.description,
                            playbook_rule=rule.id,
                            recommended_language=rule.recommended_language,
                            clause_text=text[:500],
                        )
                    )

        return flags

    def missing_clauses(self, result: object) -> list[str]:
        """
        Return a list of required CUAD clause types that are absent from *result*.

        This is separate from the per-rule flag_if_missing checks — it compares
        the full set of required_clauses in the playbook against what was extracted.

        Args:
            result: Any object with a .clauses attribute.

        Returns:
            list[str] — CUAD clause type identifiers that are missing.
        """
        clauses = _get_clauses(result)
        present: set[str] = {_clause_type(c) for c in clauses}
        return [ct for ct in self.playbook.required_clauses if ct not in present]
