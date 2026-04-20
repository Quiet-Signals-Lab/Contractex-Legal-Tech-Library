"""Standard NDA playbook.

Covers mutual and one-sided NDAs.  Override individual rules in a
subclass to adapt for specific client positions.

Usage::

    from contractex.playbooks import StandardNDAPlaybook
    from contractex.analysis import RiskAnalyzer

    analyzer = RiskAnalyzer(playbook=StandardNDAPlaybook())
    risks = analyzer.analyze(extraction_result)
"""

from __future__ import annotations

from contractex.playbooks.base import Playbook, PlaybookRule, RiskSeverity


class StandardNDAPlaybook(Playbook):
    """
    Standard NDA / non-disclosure agreement playbook.

    Flags common issues: one-sided indemnification, overly broad scope,
    missing mutual obligations, indefinite term, no return-of-information
    clause.
    """

    def __init__(self) -> None:
        super().__init__(
            name="Standard NDA",
            version="1.0",
            description=(
                "Risk rules for mutual and one-sided non-disclosure agreements. "
                "Covers indemnification balance, scope, term, and return of information."
            ),
            required_clauses=[
                "confidentiality",
                "governing_law",
                "termination_for_cause",
                "effective_date",
                "expiration_date",
            ],
            rules=[
                # ---- Indemnification ----
                PlaybookRule(
                    id="nda.indemnification.must_be_bilateral",
                    clause_type="indemnification",
                    description=(
                        "Indemnification appears one-sided. A mutual NDA should "
                        "impose reciprocal indemnification obligations on both parties."
                    ),
                    severity=RiskSeverity.HIGH,
                    recommended_language=(
                        "Each party (the 'Indemnifying Party') shall indemnify, defend, "
                        "and hold harmless the other party from any losses arising from "
                        "the Indemnifying Party's breach of this Agreement."
                    ),
                    required_keywords=["each party", "mutual", "both parties"],
                ),
                # ---- Limitation of liability ----
                PlaybookRule(
                    id="nda.liability.no_cap",
                    clause_type="uncapped_liability",
                    description=(
                        "No cap on liability. Unlimited exposure is a critical risk "
                        "for the disclosing party."
                    ),
                    severity=RiskSeverity.CRITICAL,
                    recommended_language=(
                        "Each party's aggregate liability shall not exceed the greater of "
                        "[AMOUNT] or the amounts paid in the twelve (12) months prior "
                        "to the claim."
                    ),
                    forbidden_keywords=[],
                    flag_if_missing=False,
                    forbidden_pattern=r"(unlimited|no\s+limit|uncapped)\s+liabilit",
                ),
                # ---- Scope ----
                PlaybookRule(
                    id="nda.scope.overly_broad",
                    clause_type="confidentiality",
                    description=(
                        "Confidentiality scope may be overbroad — 'all information' "
                        "without carve-outs creates unreasonable obligations."
                    ),
                    severity=RiskSeverity.MEDIUM,
                    recommended_language=(
                        "Confidential Information shall not include information that: "
                        "(a) is or becomes publicly known through no act of the recipient; "
                        "(b) was rightfully known to the recipient prior to disclosure; "
                        "(c) is independently developed by the recipient."
                    ),
                    required_keywords=[
                        "publicly available",
                        "public domain",
                        "independently developed",
                    ],
                ),
                # ---- Term ----
                PlaybookRule(
                    id="nda.term.indefinite",
                    clause_type="expiration_date",
                    description=(
                        "NDA term appears indefinite or missing. Most jurisdictions "
                        "disfavour perpetual confidentiality obligations."
                    ),
                    severity=RiskSeverity.MEDIUM,
                    recommended_language=(
                        "The confidentiality obligations in this Agreement shall survive "
                        "termination for a period of [X] years."
                    ),
                    required_keywords=["years", "months", "period"],
                ),
                # ---- Return of information ----
                PlaybookRule(
                    id="nda.return_of_info.missing",
                    clause_type="confidentiality",
                    description=(
                        "No return-of-information or destruction obligation. "
                        "Without this, the recipient can retain confidential material indefinitely."
                    ),
                    severity=RiskSeverity.MEDIUM,
                    recommended_language=(
                        "Upon request or termination, the receiving party shall promptly "
                        "return or destroy all Confidential Information and certify "
                        "such destruction in writing."
                    ),
                    required_keywords=["return", "destroy", "destruction"],
                ),
                # ---- Non-compete scope ----
                PlaybookRule(
                    id="nda.non_compete.duration",
                    clause_type="non_compete",
                    description=(
                        "Non-compete clause lacks explicit duration. "
                        "Unlimited non-competes are often unenforceable."
                    ),
                    severity=RiskSeverity.HIGH,
                    recommended_language=(
                        "The non-compete restriction shall apply for a period of "
                        "[X] years following the termination of this Agreement."
                    ),
                    required_keywords=["years", "months"],
                ),
                # ---- Governing law ----
                PlaybookRule(
                    id="nda.governing_law.missing",
                    clause_type="governing_law",
                    description="No governing law clause. Dispute resolution will be uncertain.",
                    severity=RiskSeverity.HIGH,
                    recommended_language=(
                        "This Agreement shall be governed by and construed in accordance "
                        "with the laws of the State of [STATE], without regard to its "
                        "conflict of laws provisions."
                    ),
                    flag_if_missing=True,
                ),
            ],
        )
