"""
CUAD (Contract Understanding Atticus Dataset) taxonomy definitions.

CUAD defines 41 common clause types found in commercial contracts.
"""

from enum import Enum


class CUADClauseType(str, Enum):
    """
    CUAD clause type enumeration.

    Based on the CUAD dataset: https://www.atticusprojectai.org/cuad
    """

    # Agreement and Parties
    PARTIES = "parties"
    DOCUMENT_NAME = "document_name"
    EFFECTIVE_DATE = "effective_date"
    EXPIRATION_DATE = "expiration_date"
    RENEWAL_TERM = "renewal_term"
    AGREEMENT_DATE = "agreement_date"

    # Termination
    TERMINATION_FOR_CAUSE = "termination_for_cause"
    TERMINATION_FOR_CONVENIENCE = "termination_for_convenience"
    NOTICE_PERIOD_TO_TERMINATE = "notice_period_to_terminate"

    # Financial Terms
    PAYMENT_TERMS = "payment_terms"
    CAP_ON_LIABILITY = "cap_on_liability"
    LIQUIDATED_DAMAGES = "liquidated_damages"
    PRICE_RESTRICTIONS = "price_restrictions"

    # Intellectual Property
    LICENSE_GRANT = "license_grant"
    IP_OWNERSHIP_ASSIGNMENT = "ip_ownership_assignment"
    JOINT_IP_OWNERSHIP = "joint_ip_ownership"

    # Non-Compete and Restrictions
    NON_COMPETE = "non_compete"
    EXCLUSIVITY = "exclusivity"
    NO_SOLICIT_OF_CUSTOMERS = "no_solicit_of_customers"
    NO_SOLICIT_OF_EMPLOYEES = "no_solicit_of_employees"

    # Confidentiality and Data
    CONFIDENTIALITY = "confidentiality"
    DATA_SECURITY = "data_security"
    AUDIT_RIGHTS = "audit_rights"

    # Liability and Indemnification
    UNCAPPED_LIABILITY = "uncapped_liability"
    INDEMNIFICATION = "indemnification"
    INSURANCE_REQUIREMENTS = "insurance_requirements"
    WARRANTY_DISCLAIMER = "warranty_disclaimer"

    # Changes and Updates
    CHANGE_OF_CONTROL = "change_of_control"
    ANTI_ASSIGNMENT = "anti_assignment"
    CONTRACT_MODIFICATION = "contract_modification"

    # Dispute Resolution
    GOVERNING_LAW = "governing_law"
    VENUE = "venue"
    ARBITRATION = "arbitration"

    # Revenue and Performance
    REVENUE_PROFIT_SHARING = "revenue_profit_sharing"
    MINIMUM_COMMITMENT = "minimum_commitment"
    VOLUME_RESTRICTION = "volume_restriction"
    MOST_FAVORED_NATION = "most_favored_nation"

    # Authority and Compliance
    AUTHORITY = "authority"
    THIRD_PARTY_BENEFICIARIES = "third_party_beneficiaries"
    ROFR_ROFO_ROFN = "rofr_rofo_rofn"  # Right of First Refusal/Offer/Negotiation

    # Other
    MISCELLANEOUS = "miscellaneous"

    @classmethod
    def get_description(cls, clause_type: "CUADClauseType") -> str:
        """
        Get human-readable description of a clause type.

        Args:
            clause_type: CUAD clause type

        Returns:
            Description of the clause type
        """
        descriptions = {
            cls.PARTIES: "Identifies the parties entering into the agreement",
            cls.DOCUMENT_NAME: "The name or title of the agreement",
            cls.EFFECTIVE_DATE: "When the agreement becomes effective",
            cls.EXPIRATION_DATE: "When the agreement expires or ends",
            cls.RENEWAL_TERM: "Terms for automatic renewal or extension",
            cls.AGREEMENT_DATE: "Date the agreement was executed",
            cls.TERMINATION_FOR_CAUSE: "Conditions allowing termination due to breach or fault",
            cls.TERMINATION_FOR_CONVENIENCE: "Ability to terminate without cause",
            cls.NOTICE_PERIOD_TO_TERMINATE: "Required notice period for termination",
            cls.PAYMENT_TERMS: "Payment amounts, schedule, and conditions",
            cls.CAP_ON_LIABILITY: "Maximum liability limits",
            cls.LIQUIDATED_DAMAGES: "Pre-determined damages for breach",
            cls.PRICE_RESTRICTIONS: "Restrictions on pricing or price changes",
            cls.LICENSE_GRANT: "Grant of license for intellectual property use",
            cls.IP_OWNERSHIP_ASSIGNMENT: "Transfer of IP ownership",
            cls.JOINT_IP_OWNERSHIP: "Shared ownership of intellectual property",
            cls.NON_COMPETE: "Restriction on competing activities",
            cls.EXCLUSIVITY: "Exclusive rights or obligations",
            cls.NO_SOLICIT_OF_CUSTOMERS: "Prohibition on soliciting customers",
            cls.NO_SOLICIT_OF_EMPLOYEES: "Prohibition on hiring employees",
            cls.CONFIDENTIALITY: "Confidentiality and non-disclosure obligations",
            cls.DATA_SECURITY: "Data protection and security requirements",
            cls.AUDIT_RIGHTS: "Rights to audit records or compliance",
            cls.UNCAPPED_LIABILITY: "Unlimited liability exposure",
            cls.INDEMNIFICATION: "Obligation to indemnify against losses",
            cls.INSURANCE_REQUIREMENTS: "Required insurance coverage",
            cls.WARRANTY_DISCLAIMER: "Disclaimer of warranties",
            cls.CHANGE_OF_CONTROL: "Provisions triggered by change in ownership",
            cls.ANTI_ASSIGNMENT: "Restrictions on transferring the agreement",
            cls.CONTRACT_MODIFICATION: "How the contract can be modified or amended",
            cls.GOVERNING_LAW: "Which jurisdiction's laws govern the agreement",
            cls.VENUE: "Where disputes must be resolved",
            cls.ARBITRATION: "Requirement to arbitrate disputes",
            cls.REVENUE_PROFIT_SHARING: "Revenue or profit sharing arrangements",
            cls.MINIMUM_COMMITMENT: "Minimum purchase or usage commitments",
            cls.VOLUME_RESTRICTION: "Maximum volume or quantity restrictions",
            cls.MOST_FAVORED_NATION: "Obligation to offer best pricing terms",
            cls.AUTHORITY: "Representation that party has authority to enter agreement",
            cls.THIRD_PARTY_BENEFICIARIES: "Third parties who can enforce the agreement",
            cls.ROFR_ROFO_ROFN: "Right of first refusal, offer, or negotiation",
            cls.MISCELLANEOUS: "Other standard contract provisions",
        }

        return descriptions.get(clause_type, "")

    @classmethod
    def get_all_types(cls) -> list:
        """Get list of all CUAD clause types."""
        return list(cls)

    @classmethod
    def get_high_risk_types(cls) -> list:
        """Get clause types that typically represent higher risk."""
        return [
            cls.UNCAPPED_LIABILITY,
            cls.NON_COMPETE,
            cls.EXCLUSIVITY,
            cls.AUTO_RENEWAL,
            cls.ANTI_ASSIGNMENT,
            cls.LIQUIDATED_DAMAGES,
            cls.WARRANTY_DISCLAIMER,
        ]
