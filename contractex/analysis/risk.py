"""
Playbook-based risk analysis — Layer 3.

RiskAnalyzer takes an extraction result (or a list of clauses) and a
Playbook, evaluates every rule deterministically, and returns a list of
PlaybookFlag objects.

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

from contractex.analysis.compare import _clause_ref, _clause_text, _clause_type, _get_clauses
from contractex.playbooks.base import Playbook, RiskSeverity

# ---------------------------------------------------------------------------
# Analysis output types (separate from core models to keep the analysis
# module self-contained and importable without heavy core dependencies)
# ---------------------------------------------------------------------------


@dataclass
class PlaybookFlag:
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

    def analyze(self, result: object) -> list[PlaybookFlag]:
        """
        Run all playbook rules against *result* and return a list of flags.

        Args:
            result: Any object with a .clauses attribute (Contract, ExtractionResult,
                    or a list of Clause objects).

        Returns:
            list[PlaybookFlag] — one entry per rule that fired.
        """
        clauses = _get_clauses(result)
        clause_types_present: set[str] = {_clause_type(c) for c in clauses}
        flags: list[PlaybookFlag] = []

        for rule in self.playbook.rules:
            # Missing-clause check
            if rule.flag_if_missing and rule.clause_type not in clause_types_present:
                flags.append(
                    PlaybookFlag(
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
                        PlaybookFlag(
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


def __getattr__(name: str) -> object:
    # RiskFlag was renamed: the same name also meant contractex.core.models.RiskFlag.
    if name == "RiskFlag":
        import warnings

        warnings.warn(
            "contractex.analysis.risk.RiskFlag is now PlaybookFlag; the old name will be removed.",
            DeprecationWarning,
            stacklevel=2,
        )
        return PlaybookFlag
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
