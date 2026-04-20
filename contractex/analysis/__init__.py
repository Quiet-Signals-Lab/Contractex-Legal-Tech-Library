"""
contractex.analysis — Layer 3: Analysis built on top of extraction results.

Analysis operates on extraction results, not raw documents.  This means
you can run extraction once, serialize the result, and run different analyses
without re-invoking any LLM.

Public API::

    from contractex.analysis import RiskAnalyzer, ObligationTimeline, compare
    from contractex.playbooks import StandardNDAPlaybook

    # Playbook-based risk analysis (no LLM)
    analyzer = RiskAnalyzer(playbook=StandardNDAPlaybook())
    risks = analyzer.analyze(extraction_result)
    gaps = analyzer.missing_clauses(extraction_result)

    # Obligation timeline with iCal export
    timeline = ObligationTimeline(
        obligations=extraction_result.obligations,
        effective_date="2024-01-01"
    )
    upcoming = timeline.upcoming(days=30)
    ics = timeline.to_ical()

    # Contract version comparison
    diff = compare(result_v1, result_v2)
    print(diff.summary())
"""

from contractex.analysis.compare import ClauseChange, ContractDiff, compare
from contractex.analysis.risk import RiskAnalyzer, RiskFlag
from contractex.analysis.timeline import ObligationEntry, ObligationTimeline

__all__ = [
    "RiskAnalyzer",
    "RiskFlag",
    "ObligationTimeline",
    "ObligationEntry",
    "compare",
    "ContractDiff",
    "ClauseChange",
]
