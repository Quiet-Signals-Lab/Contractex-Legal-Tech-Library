"""
Clause classifier for categorizing contract clauses using CUAD taxonomy or custom types.
"""

from __future__ import annotations

from contractex.core.models import Clause, Contract
from contractex.taxonomy.cuad import CUADClauseType

# Keyword map for rule-based classification.
# Each entry maps a CUADClauseType value to a list of indicative keywords.
_KEYWORD_MAP: dict[str, list[str]] = {
    CUADClauseType.TERMINATION_FOR_CAUSE.value: [
        "terminate for cause",
        "material breach",
        "default",
        "cure period",
    ],
    CUADClauseType.TERMINATION_FOR_CONVENIENCE.value: [
        "terminate for convenience",
        "terminate without cause",
        "at its sole discretion",
    ],
    CUADClauseType.NOTICE_PERIOD_TO_TERMINATE.value: [
        "days' notice",
        "days notice",
        "written notice of termination",
    ],
    CUADClauseType.PAYMENT_TERMS.value: [
        "payment",
        "invoice",
        "net 30",
        "net 60",
        "fee",
        "remit",
    ],
    CUADClauseType.CAP_ON_LIABILITY.value: [
        "liability shall not exceed",
        "aggregate liability",
        "cap on liability",
        "maximum liability",
    ],
    CUADClauseType.UNCAPPED_LIABILITY.value: [
        "unlimited liability",
        "no limit on liability",
        "no cap",
    ],
    CUADClauseType.LIQUIDATED_DAMAGES.value: [
        "liquidated damages",
        "penalty",
        "pre-agreed damages",
    ],
    CUADClauseType.INDEMNIFICATION.value: [
        "indemnif",
        "hold harmless",
        "defend",
        "indemnitor",
    ],
    CUADClauseType.CONFIDENTIALITY.value: [
        "confidential",
        "non-disclosure",
        "proprietary information",
        "trade secret",
    ],
    CUADClauseType.GOVERNING_LAW.value: [
        "governed by",
        "governing law",
        "laws of the state",
        "applicable law",
    ],
    CUADClauseType.ARBITRATION.value: [
        "arbitration",
        "arbitrator",
        "aaa rules",
        "jams",
        "binding arbitration",
    ],
    CUADClauseType.VENUE.value: [
        "venue",
        "jurisdiction",
        "courts of",
        "exclusive jurisdiction",
    ],
    CUADClauseType.IP_OWNERSHIP_ASSIGNMENT.value: [
        "assigns all",
        "intellectual property rights",
        "work made for hire",
        "assigns to",
        "vests in",
    ],
    CUADClauseType.LICENSE_GRANT.value: [
        "license",
        "non-exclusive",
        "royalty-free",
        "sublicense",
        "right to use",
    ],
    CUADClauseType.NON_COMPETE.value: [
        "non-compete",
        "not compete",
        "refrain from competing",
        "competing business",
    ],
    CUADClauseType.EXCLUSIVITY.value: [
        "exclusive",
        "exclusivity",
        "sole and exclusive",
    ],
    CUADClauseType.NO_SOLICIT_OF_EMPLOYEES.value: [
        "no solicit",
        "non-solicitation",
        "solicit employees",
    ],
    CUADClauseType.NO_SOLICIT_OF_CUSTOMERS.value: [
        "solicit customers",
        "solicit clients",
        "solicit business",
    ],
    CUADClauseType.ANTI_ASSIGNMENT.value: [
        "shall not assign",
        "may not assign",
        "without prior written consent",
        "anti-assignment",
    ],
    CUADClauseType.CHANGE_OF_CONTROL.value: [
        "change of control",
        "merger",
        "acquisition",
        "change in ownership",
    ],
    CUADClauseType.WARRANTY_DISCLAIMER.value: [
        "as is",
        "disclaimer of warranties",
        "no warranty",
        "disclaim",
    ],
    CUADClauseType.INSURANCE_REQUIREMENTS.value: [
        "insurance",
        "general liability",
        "workers compensation",
        "certificate of insurance",
    ],
    CUADClauseType.DATA_SECURITY.value: [
        "data security",
        "security measures",
        "personal data",
        "gdpr",
        "data protection",
    ],
    CUADClauseType.AUDIT_RIGHTS.value: [
        "audit",
        "right to audit",
        "inspect records",
        "audit rights",
    ],
    CUADClauseType.RENEWAL_TERM.value: [
        "automatically renew",
        "auto-renew",
        "renewal term",
        "evergreen",
    ],
    CUADClauseType.EFFECTIVE_DATE.value: [
        "effective date",
        "effective as of",
        "commencement date",
    ],
    CUADClauseType.EXPIRATION_DATE.value: [
        "expiration date",
        "expires on",
        "term ends",
        "end date",
    ],
    CUADClauseType.CONTRACT_MODIFICATION.value: [
        "amendment",
        "modify",
        "modification",
        "may be amended",
        "addendum",
    ],
    CUADClauseType.REVENUE_PROFIT_SHARING.value: [
        "revenue share",
        "profit sharing",
        "royalty",
        "commission",
    ],
    CUADClauseType.MINIMUM_COMMITMENT.value: [
        "minimum purchase",
        "minimum commitment",
        "minimum order",
        "take-or-pay",
    ],
    CUADClauseType.MOST_FAVORED_NATION.value: [
        "most favored nation",
        "most-favored-nation",
        "mfn",
    ],
    CUADClauseType.ROFR_ROFO_ROFN.value: [
        "right of first refusal",
        "right of first offer",
        "rofr",
        "rofo",
    ],
}


class CUADClassifier:
    """
    Classifier for categorizing contract clauses according to CUAD taxonomy.

    CUAD (Contract Understanding Atticus Dataset) defines 41 common clause types
    found in commercial contracts.

    Classification uses keyword-based rules. Set ``use_llm=True`` and provide
    an LLM provider to augment with LLM-based classification (not yet
    implemented — contributions welcome).
    """

    def __init__(
        self,
        clause_types: list[str] | None = None,
        multi_label: bool = True,
        confidence_threshold: float = 0.5,
        use_llm: bool = False,
    ):
        """
        Initialize the CUAD classifier.

        Args:
            clause_types: Specific clause types to classify (None = all CUAD types)
            multi_label: Whether a clause can have multiple types
            confidence_threshold: Confidence score assigned to keyword matches
            use_llm: Reserved for future LLM-based classification (currently ignored)
        """
        self.clause_types = clause_types or self._get_all_cuad_types()
        self.multi_label = multi_label
        self.confidence_threshold = confidence_threshold
        self.use_llm = use_llm
        # Filter keyword map to only include requested clause types
        self._active_keywords = {k: v for k, v in _KEYWORD_MAP.items() if k in self.clause_types}

    def _get_all_cuad_types(self) -> list[str]:
        """Get all CUAD clause types."""
        return [ct.value for ct in CUADClauseType]

    def classify(self, contract: Contract) -> list[Clause]:
        """
        Classify all clauses in a contract.

        Args:
            contract: Contract with clauses to classify

        Returns:
            List of classified clauses with updated clause_type
        """
        return [self.classify_clause(clause) for clause in contract.clauses]

    def classify_clause(self, clause: Clause) -> Clause:
        """
        Classify a single clause using keyword matching.

        The first matching type is assigned to ``clause.clause_type``. When
        ``multi_label=True``, all matches are stored in
        ``clause.metadata["all_types"]``.

        Args:
            clause: Clause to classify

        Returns:
            Clause with updated clause_type, confidence, and metadata
        """
        matched = self.classify_text(clause.text)
        if matched:
            clause.clause_type = matched[0]
            clause.confidence = self.confidence_threshold
            if self.multi_label:
                clause.metadata["all_types"] = matched
        return clause

    def classify_text(self, text: str) -> list[str]:
        """
        Classify arbitrary text into CUAD clause types using keyword matching.

        Args:
            text: Text to classify

        Returns:
            List of matching clause type values ordered by first keyword hit
        """
        text_lower = text.lower()
        matched: list[str] = []
        for clause_type, keywords in self._active_keywords.items():
            if any(kw in text_lower for kw in keywords):
                matched.append(clause_type)
                if not self.multi_label:
                    break
        return matched
