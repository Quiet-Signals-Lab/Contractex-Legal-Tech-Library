"""
Internal Pydantic schemas for LLM structured output.

These schemas are the intermediate shapes the LLM fills in — they are NOT
the public contract models (contractex.core.models).  They use forgiving
defaults and Optional fields so that partial or slightly malformed LLM
responses don't crash the pipeline.

After extraction the caller is responsible for:
  - Mapping schema values to public enums (ContractType, PartyRole, …)
  - Parsing date strings via DateNormalizer
  - Parsing amount strings via CurrencyNormalizer
  - Deduplicating results across chunks
"""

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Contract info + parties  (Phase 1 — preamble extraction)
# ---------------------------------------------------------------------------


class LLMPartyResult(BaseModel):
    """A single contracting party extracted by the LLM."""

    name: str = Field(..., description="Full legal name of the entity or person")
    role: Optional[str] = Field(
        None,
        description=(
            "Role in the contract. Must be one of: provider, client, licensor, "
            "licensee, buyer, seller, employer, employee, landlord, tenant, partner, other"
        ),
    )
    entity_type: Optional[str] = Field(
        None,
        description="Legal form of the entity (e.g. corporation, LLC, individual, partnership)",
    )
    jurisdiction: Optional[str] = Field(
        None,
        description="State or country of incorporation (e.g. 'Delaware', 'England and Wales')",
    )
    address: Optional[str] = Field(None, description="Physical or registered address if stated")
    confidence: float = Field(
        0.7,
        ge=0.0,
        le=1.0,
        description="Confidence that this extraction is accurate (0.0–1.0)",
    )


class LLMContractInfoResponse(BaseModel):
    """
    Contract-level metadata and parties extracted from the opening section.

    This schema is used for Phase 1: a single LLM call over the first 1-2 chunks
    to capture everything that appears in the contract header / preamble.
    """

    contract_type: Optional[str] = Field(
        None,
        description=(
            "Contract type. Must be one of: nda, master_service_agreement, "
            "statement_of_work, employment_agreement, lease_agreement, "
            "purchase_agreement, license_agreement, partnership_agreement, "
            "joint_venture, franchise_agreement, distribution_agreement, "
            "reseller_agreement, consulting_agreement, unknown"
        ),
    )
    title: Optional[str] = Field(None, description="Official title of the agreement")
    effective_date: Optional[str] = Field(
        None,
        description="Effective date as a string (e.g. 'January 1, 2024' or '2024-01-01')",
    )
    expiration_date: Optional[str] = Field(
        None,
        description="Expiration or end date as a string",
    )
    signature_date: Optional[str] = Field(
        None,
        description="Date the agreement was signed, as a string",
    )
    governing_law: Optional[str] = Field(
        None,
        description="Jurisdiction whose laws govern this agreement (e.g. 'State of New York')",
    )
    parties: list[LLMPartyResult] = Field(
        default_factory=list,
        description="All primary contracting parties (not incidentally mentioned third parties)",
    )


# ---------------------------------------------------------------------------
# Clause extraction  (Phase 2 — per-chunk)
# ---------------------------------------------------------------------------


class LLMClauseResult(BaseModel):
    """A single clause identified in a contract chunk."""

    clause_type: str = Field(
        ...,
        description=(
            "CUAD clause type. Must be one of the values listed in the prompt. "
            "Use 'miscellaneous' if no specific type fits."
        ),
    )
    text: str = Field(..., description="Complete verbatim text of the clause")
    section_number: Optional[str] = Field(
        None,
        description="Section identifier as it appears in the document (e.g. '8.2', 'Article IV')",
    )
    confidence: float = Field(
        0.7,
        ge=0.0,
        le=1.0,
        description="Confidence in the clause type classification (0.0–1.0)",
    )


class LLMClausesResponse(BaseModel):
    """Clauses extracted from a single chunk."""

    clauses: list[LLMClauseResult] = Field(
        default_factory=list,
        description="All significant clauses found in this section of the contract",
    )


# ---------------------------------------------------------------------------
# Financial term extraction  (Phase 2 — per-chunk, combined with clauses)
# ---------------------------------------------------------------------------


class LLMFinancialResult(BaseModel):
    """A single financial obligation or term extracted from a contract chunk."""

    term_type: str = Field(
        ...,
        description=(
            "Type of financial term, e.g.: payment_amount, service_fee, license_fee, "
            "royalty, commission, bonus, penalty, deposit, reimbursement, insurance_minimum"
        ),
    )
    amount: Optional[str] = Field(
        None,
        description=(
            "Numeric amount as a plain string without commas or currency symbols "
            "(e.g. '50000.00' or '1500'). Null if variable or not specified."
        ),
    )
    currency: str = Field(
        "USD",
        description="ISO 4217 currency code (e.g. 'USD', 'EUR', 'GBP'). Default: USD",
    )
    frequency: Optional[str] = Field(
        None,
        description=(
            "Payment frequency. Must be one of: one-time, monthly, quarterly, "
            "annually, weekly, per-use, or null if not applicable"
        ),
    )
    due_date: Optional[str] = Field(
        None,
        description="Due date or payment trigger as a string (e.g. 'net 30', 'upon delivery')",
    )
    description: str = Field(
        "",
        description="Brief description of what this financial term covers",
    )
    conditions: list[str] = Field(
        default_factory=list,
        description="Conditions or triggers that apply to this term",
    )
    confidence: float = Field(
        0.7,
        ge=0.0,
        le=1.0,
        description="Confidence in the extraction accuracy (0.0–1.0)",
    )


class LLMFinancialResponse(BaseModel):
    """Financial terms extracted from a single chunk."""

    financial_terms: list[LLMFinancialResult] = Field(
        default_factory=list,
        description="All financial obligations, fees, and payments found in this section",
    )


# ---------------------------------------------------------------------------
# Combined single-chunk extraction  (used when entire contract fits one call)
# ---------------------------------------------------------------------------


class LLMFullExtractionResponse(BaseModel):
    """
    Single-call full extraction for short contracts or large-context models.

    Combines contract info, parties, clauses, and financial terms in one
    structured output.  Used when the entire contract fits in one chunk.
    """

    contract_type: Optional[str] = None
    title: Optional[str] = None
    effective_date: Optional[str] = None
    expiration_date: Optional[str] = None
    signature_date: Optional[str] = None
    governing_law: Optional[str] = None
    parties: list[LLMPartyResult] = Field(default_factory=list)
    clauses: list[LLMClauseResult] = Field(default_factory=list)
    financial_terms: list[LLMFinancialResult] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Risk analysis  (post-extraction, optional LLM pass)
# ---------------------------------------------------------------------------


class LLMRiskResult(BaseModel):
    """A single risk identified in the contract by the LLM."""

    risk_type: str = Field(..., description="Short identifier for this risk category")
    severity: str = Field(
        ...,
        description="Risk severity: critical, high, medium, low, or info",
    )
    description: str = Field(..., description="Clear explanation of the risk")
    clause_reference: Optional[str] = Field(
        None,
        description="Section number or heading where this risk appears",
    )
    clause_text: Optional[str] = Field(
        None,
        description="Relevant excerpt (up to 200 characters) showing the risk",
    )
    recommendation: Optional[str] = Field(
        None,
        description="Suggested action to mitigate or negotiate away this risk",
    )
    impact: Optional[str] = Field(
        None,
        description="Potential business or financial consequences if this risk materialises",
    )
    confidence: float = Field(
        0.8,
        ge=0.0,
        le=1.0,
        description="Confidence that this is a genuine risk (0.0–1.0)",
    )


class LLMRiskResponse(BaseModel):
    """Risks identified by the LLM in the contract."""

    risks: list[LLMRiskResult] = Field(
        default_factory=list,
        description="All risks identified, ordered by severity (critical first)",
    )
