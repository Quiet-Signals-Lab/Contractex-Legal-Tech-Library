"""SaaS / software licence playbook.

Covers recurring-revenue SaaS agreements and perpetual software licences.
Inherits nothing from the NDA playbook — different practice area.

Usage::

    from contractex.playbooks import SaaSPlaybook
    from contractex.analysis import RiskAnalyzer

    analyzer = RiskAnalyzer(playbook=SaaSPlaybook())
    risks = analyzer.analyze(extraction_result)
"""

from __future__ import annotations

from contractex.playbooks.base import Playbook, PlaybookRule, RiskSeverity


class SaaSPlaybook(Playbook):
    """
    Risk rules for SaaS subscription and software licence agreements.

    Covers: uncapped liability, data-security obligations, auto-renewal
    traps, audit rights, change-of-control, uptime SLAs.
    """

    def __init__(self) -> None:
        super().__init__(
            name="SaaS / Software Licence",
            version="1.0",
            description=(
                "Risk rules for SaaS and software licence agreements. "
                "Prioritises data security, liability exposure, and renewal traps."
            ),
            required_clauses=[
                "data_security",
                "cap_on_liability",
                "governing_law",
                "effective_date",
                "renewal_term",
                "termination_for_cause",
                "indemnification",
            ],
            rules=[
                # ---- Liability cap ----
                PlaybookRule(
                    id="saas.liability.no_cap",
                    clause_type="cap_on_liability",
                    description=(
                        "No liability cap. SaaS vendors should cap aggregate liability "
                        "at fees paid in the preceding 12 months."
                    ),
                    severity=RiskSeverity.CRITICAL,
                    recommended_language=(
                        "Vendor's aggregate liability shall not exceed the fees paid by "
                        "Customer in the twelve (12) months preceding the claim."
                    ),
                    flag_if_missing=True,
                ),
                # ---- Data security ----
                PlaybookRule(
                    id="saas.data_security.no_breach_notification",
                    clause_type="data_security",
                    description=(
                        "Data security clause does not include breach notification "
                        "obligations. Regulatory frameworks (GDPR, CCPA) require "
                        "timely notification."
                    ),
                    severity=RiskSeverity.HIGH,
                    recommended_language=(
                        "Vendor shall notify Customer of any confirmed Security Incident "
                        "within 72 hours of discovery."
                    ),
                    required_keywords=["notify", "notification", "breach notification", "72 hours"],
                ),
                # ---- Auto-renewal trap ----
                PlaybookRule(
                    id="saas.renewal.auto_renewal_without_notice",
                    clause_type="renewal_term",
                    description=(
                        "Auto-renewal clause does not require advance notice to Customer. "
                        "Customer may be locked into an unwanted renewal term."
                    ),
                    severity=RiskSeverity.HIGH,
                    recommended_language=(
                        "Vendor shall provide Customer with at least 60 days' written "
                        "notice prior to any automatic renewal."
                    ),
                    required_keywords=["notice", "notify", "written notice"],
                ),
                # ---- Change of control ----
                PlaybookRule(
                    id="saas.change_of_control.missing",
                    clause_type="change_of_control",
                    description=(
                        "No change-of-control clause. A vendor acquisition could result "
                        "in Customer's data being transferred to a competitor."
                    ),
                    severity=RiskSeverity.HIGH,
                    recommended_language=(
                        "Customer may terminate this Agreement on 30 days' notice if "
                        "Vendor undergoes a Change of Control to a direct competitor "
                        "of Customer."
                    ),
                    flag_if_missing=True,
                ),
                # ---- Audit rights ----
                PlaybookRule(
                    id="saas.audit.missing",
                    clause_type="audit_rights",
                    description=(
                        "No audit rights for Customer. Without these, Customer cannot "
                        "verify security controls or licence compliance."
                    ),
                    severity=RiskSeverity.MEDIUM,
                    recommended_language=(
                        "Vendor shall provide Customer with annual SOC 2 Type II reports "
                        "and permit Customer to conduct security audits on 30 days' notice."
                    ),
                    flag_if_missing=True,
                ),
                # ---- Uptime SLA ----
                PlaybookRule(
                    id="saas.sla.no_uptime_commitment",
                    clause_type="miscellaneous",
                    description=(
                        "No uptime SLA. Without a committed availability level, "
                        "Customer has no contractual remedy for outages."
                    ),
                    severity=RiskSeverity.MEDIUM,
                    recommended_language=(
                        "Vendor commits to 99.9% monthly uptime, excluding scheduled "
                        "maintenance windows communicated with 48 hours' notice."
                    ),
                    required_keywords=["uptime", "availability", "sla", "service level"],
                ),
                # ---- IP ownership ----
                PlaybookRule(
                    id="saas.ip.customer_data_ownership",
                    clause_type="ip_ownership_assignment",
                    description=(
                        "IP ownership clause does not explicitly state that Customer "
                        "retains ownership of its data submitted to the service."
                    ),
                    severity=RiskSeverity.HIGH,
                    recommended_language=(
                        "As between the parties, Customer retains all right, title, "
                        "and interest in and to Customer Data."
                    ),
                    required_keywords=["customer data", "customer retains", "customer owns"],
                ),
            ],
        )
