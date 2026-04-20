"""
Core Pydantic models for contract intelligence.

These models represent the structured data extracted from legal documents,
providing type-safe interfaces with validation and convenience methods.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    import pandas as pd


class ContractType(str, Enum):
    """Common contract types."""

    NDA = "nda"
    MSA = "master_service_agreement"
    SOW = "statement_of_work"
    EMPLOYMENT = "employment_agreement"
    LEASE = "lease_agreement"
    PURCHASE = "purchase_agreement"
    LICENSE = "license_agreement"
    PARTNERSHIP = "partnership_agreement"
    JOINT_VENTURE = "joint_venture"
    FRANCHISE = "franchise_agreement"
    DISTRIBUTION = "distribution_agreement"
    RESELLER = "reseller_agreement"
    CONSULTING = "consulting_agreement"
    UNKNOWN = "unknown"


class PartyRole(str, Enum):
    """Roles that parties can have in a contract."""

    PROVIDER = "provider"
    CLIENT = "client"
    LICENSOR = "licensor"
    LICENSEE = "licensee"
    BUYER = "buyer"
    SELLER = "seller"
    EMPLOYER = "employer"
    EMPLOYEE = "employee"
    LANDLORD = "landlord"
    TENANT = "tenant"
    PARTNER = "partner"
    OTHER = "other"


class RiskSeverity(str, Enum):
    """Risk severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class Party(BaseModel):
    """Represents a party (legal entity) in a contract."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "Acme Corporation",
                "role": "provider",
                "entity_type": "corporation",
                "jurisdiction": "Delaware",
                "contact_info": {"email": "legal@acme.com"},
                "confidence": 0.95,
            }
        }
    )

    name: str = Field(..., description="Legal name of the party")
    role: PartyRole | None = Field(None, description="Role in the contract")
    entity_type: str | None = Field(None, description="Type of entity (LLC, Corp, etc.)")
    jurisdiction: str | None = Field(None, description="Jurisdiction of incorporation")
    contact_info: dict[str, Any] = Field(default_factory=dict, description="Contact information")
    address: str | None = Field(None, description="Physical address")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Extraction confidence score")

    def __str__(self) -> str:
        return f"{self.name} ({self.role})" if self.role else self.name


class Clause(BaseModel):
    """Represents an extracted clause from a contract."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "clause_type": "termination",
                "text": "Either party may terminate this agreement...",
                "page_number": 5,
                "confidence": 0.92,
                "tags": ["termination", "notice_period"],
            }
        }
    )

    clause_type: str = Field(..., description="Type/category of the clause")
    text: str = Field(..., description="Full text of the clause")
    page_number: int | None = Field(None, description="Page number where clause appears")
    section_number: str | None = Field(None, description="Section number (e.g., '3.2.1')")

    # Spatial metadata for visual grounding
    bbox: dict[str, float] | None = Field(
        None, description="Bounding box coordinates {x, y, width, height}"
    )

    # Extraction metadata
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Extraction confidence score")
    extracted_entities: dict[str, Any] = Field(
        default_factory=dict, description="Entities extracted from this clause"
    )
    tags: list[str] = Field(default_factory=list, description="Custom tags")

    # Relationships
    parent_clause_id: str | None = Field(None, description="ID of parent clause if nested")
    related_clauses: list[str] = Field(default_factory=list, description="IDs of related clauses")

    # Additional metadata
    metadata: dict[str, Any] = Field(default_factory=dict, description="Flexible metadata")

    def __str__(self) -> str:
        preview = self.text[:100] + "..." if len(self.text) > 100 else self.text
        return f"[{self.clause_type}] {preview}"


class FinancialTerm(BaseModel):
    """Represents financial terms extracted from a contract."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "term_type": "payment_amount",
                "amount": "50000.00",
                "currency": "USD",
                "frequency": "monthly",
                "description": "Monthly service fee",
                "confidence": 0.88,
            }
        }
    )

    term_type: str = Field(
        ..., description="Type of financial term (payment_amount, penalty, bonus, etc.)"
    )
    amount: Decimal | None = Field(None, description="Monetary amount")
    currency: str = Field("USD", description="Currency code (ISO 4217)")
    frequency: str | None = Field(
        None, description="Payment frequency (one-time, monthly, quarterly, annually)"
    )
    due_date: date | None = Field(None, description="Payment due date")
    description: str = Field("", description="Description of the financial term")
    conditions: list[str] = Field(
        default_factory=list, description="Conditions that apply to this term"
    )
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Extraction confidence score")

    def __str__(self) -> str:
        freq = f" ({self.frequency})" if self.frequency else ""
        return f"{self.term_type}: {self.currency} {self.amount}{freq}"


class RiskFlag(BaseModel):
    """Represents a potential risk identified in the contract."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "risk_type": "unlimited_liability",
                "severity": "high",
                "description": "Contract contains unlimited liability clause",
                "clause_reference": "Section 8.2",
                "recommendation": "Negotiate liability cap",
                "confidence": 0.85,
            }
        }
    )

    risk_type: str = Field(..., description="Type of risk identified")
    severity: RiskSeverity = Field(..., description="Risk severity level")
    description: str = Field(..., description="Description of the risk")
    clause_reference: str | None = Field(
        None, description="Reference to the clause containing the risk"
    )
    clause_text: str | None = Field(None, description="Text of the risky clause")
    recommendation: str | None = Field(None, description="Recommended action to mitigate risk")
    impact: str | None = Field(None, description="Potential impact of the risk")
    likelihood: str | None = Field(None, description="Likelihood of risk occurring")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Detection confidence score")

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.risk_type}: {self.description}"


class ContractMetadata(BaseModel):
    """Metadata about the contract document and extraction process."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "filename": "acme_msa_2024.pdf",
                "file_hash": "abc123...",
                "page_count": 15,
                "extraction_date": "2024-01-15T10:30:00Z",
                "llm_provider": "gpt-4o",
                "processing_time_seconds": 12.5,
            }
        }
    )

    # Document information
    filename: str | None = Field(None, description="Original filename")
    file_hash: str | None = Field(None, description="SHA-256 hash of the document")
    file_type: str | None = Field(None, description="File type (pdf, docx, etc.)")
    file_size_bytes: int | None = Field(None, description="File size in bytes")
    page_count: int | None = Field(None, description="Number of pages")

    # Extraction metadata
    extraction_date: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When extraction was performed",
    )
    llm_provider: str | None = Field(None, description="LLM provider used")
    llm_model: str | None = Field(None, description="Specific model used")
    processing_time_seconds: float | None = Field(None, description="Time taken to process")
    token_usage: dict[str, int] | None = Field(None, description="Token usage statistics")

    # Quality metrics
    overall_confidence: float | None = Field(
        None, ge=0.0, le=1.0, description="Overall extraction confidence"
    )
    warnings: list[str] = Field(default_factory=list, description="Extraction warnings")

    # Custom metadata
    custom_fields: dict[str, Any] = Field(default_factory=dict, description="User-defined metadata")


class Contract(BaseModel):
    """Main contract model representing all extracted data from a legal document."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "contract_type": "master_service_agreement",
                "title": "Master Service Agreement",
                "parties": [
                    {"name": "Acme Corp", "role": "provider"},
                    {"name": "Client Inc", "role": "client"},
                ],
                "effective_date": "2024-01-01",
                "expiration_date": "2025-01-01",
                "clauses": [],
                "financial_terms": [],
                "risks": [],
            }
        }
    )

    # Basic information
    contract_type: ContractType | None = Field(None, description="Type of contract")
    title: str | None = Field(None, description="Contract title")

    # Parties
    parties: list[Party] = Field(
        default_factory=list, description="Parties involved in the contract"
    )

    # Dates
    effective_date: date | None = Field(None, description="Contract effective date")
    expiration_date: date | None = Field(None, description="Contract expiration date")
    signature_date: date | None = Field(None, description="Date contract was signed")

    # Structural elements
    clauses: list[Clause] = Field(default_factory=list, description="Extracted clauses")
    financial_terms: list[FinancialTerm] = Field(
        default_factory=list, description="Financial terms"
    )

    # Analysis results
    risks: list[RiskFlag] = Field(default_factory=list, description="Identified risks")

    # Additional information
    governing_law: str | None = Field(None, description="Governing law jurisdiction")
    amendment_to: str | None = Field(None, description="Reference if this is an amendment")

    # Metadata
    metadata: ContractMetadata = Field(
        default_factory=lambda: ContractMetadata(),  # type: ignore[call-arg]
        description="Metadata about the document and extraction",
    )

    # Extracted text
    full_text: str | None = Field(None, description="Full extracted text")

    # Convenience properties
    @property
    def critical_risks(self) -> list[RiskFlag]:
        """Get only critical risk flags."""
        return [r for r in self.risks if r.severity == RiskSeverity.CRITICAL]

    @property
    def high_confidence_clauses(self) -> list[Clause]:
        """Get clauses with confidence >= 0.8."""
        return [c for c in self.clauses if c.confidence >= 0.8]

    @property
    def duration_days(self) -> int | None:
        """Calculate contract duration in days."""
        if self.effective_date and self.expiration_date:
            return (self.expiration_date - self.effective_date).days
        return None

    # Export methods
    def to_json(self, file_path: str | None = None, **kwargs) -> str:
        """
        Export to JSON format.

        Args:
            file_path: Optional path to save JSON file
            **kwargs: Additional arguments for json.dumps

        Returns:
            JSON string representation
        """
        json_str = self.model_dump_json(indent=2, **kwargs)

        if file_path:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(json_str)

        return json_str

    def to_dict(self) -> dict[str, Any]:
        """Export to dictionary."""
        return self.model_dump()

    def to_dataframe(self) -> pd.DataFrame:
        """
        Export to pandas DataFrame (clauses as rows).

        Returns:
            DataFrame with clause information
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas is required for to_dataframe(). Install with: pip install pandas"
            ) from e

        if not self.clauses:
            return pd.DataFrame()

        data = []
        for clause in self.clauses:
            row = {
                "contract_type": self.contract_type,
                "clause_type": clause.clause_type,
                "text": clause.text,
                "page_number": clause.page_number,
                "confidence": clause.confidence,
                "section_number": clause.section_number,
            }
            data.append(row)

        return pd.DataFrame(data)

    def to_excel(self, file_path: str) -> None:
        """
        Export to Excel file.

        Args:
            file_path: Path to save Excel file
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas and openpyxl are required. Install with: pip install pandas openpyxl"
            ) from e

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            # Contract overview
            overview_data = {
                "Field": ["Contract Type", "Title", "Effective Date", "Expiration Date", "Parties"],
                "Value": [
                    str(self.contract_type),
                    self.title or "",
                    str(self.effective_date) if self.effective_date else "",
                    str(self.expiration_date) if self.expiration_date else "",
                    ", ".join([p.name for p in self.parties]),
                ],
            }
            pd.DataFrame(overview_data).to_excel(writer, sheet_name="Overview", index=False)

            # Clauses
            if self.clauses:
                self.to_dataframe().to_excel(writer, sheet_name="Clauses", index=False)

            # Financial terms
            if self.financial_terms:
                financial_data = [
                    {
                        "Type": ft.term_type,
                        "Amount": str(ft.amount) if ft.amount else "",
                        "Currency": ft.currency,
                        "Frequency": ft.frequency or "",
                        "Description": ft.description,
                        "Confidence": ft.confidence,
                    }
                    for ft in self.financial_terms
                ]
                pd.DataFrame(financial_data).to_excel(
                    writer, sheet_name="Financial Terms", index=False
                )

            # Risks
            if self.risks:
                risk_data = [
                    {
                        "Type": r.risk_type,
                        "Severity": r.severity,
                        "Description": r.description,
                        "Recommendation": r.recommendation or "",
                        "Confidence": r.confidence,
                    }
                    for r in self.risks
                ]
                pd.DataFrame(risk_data).to_excel(writer, sheet_name="Risks", index=False)

    def compare_with(self, other: Contract) -> ContractComparison:
        """
        Compare with another contract.

        Args:
            other: Another Contract instance to compare with

        Returns:
            ContractComparison object with differences
        """
        from contractex.utils.comparators import ContractComparator

        comparator = ContractComparator()
        return comparator.compare(self, other)

    def __str__(self) -> str:
        parties_str = ", ".join([p.name for p in self.parties])
        return f"Contract({self.contract_type}, parties=[{parties_str}])"

    def __repr__(self) -> str:
        return (
            f"Contract(type={self.contract_type}, "
            f"parties={len(self.parties)}, "
            f"clauses={len(self.clauses)}, "
            f"risks={len(self.risks)})"
        )


class ContractComparison(BaseModel):
    """Results of comparing two contracts."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    contract1: Contract
    contract2: Contract

    # Differences
    party_differences: list[str] = Field(default_factory=list)
    clause_differences: list[str] = Field(default_factory=list)
    financial_differences: list[str] = Field(default_factory=list)
    date_differences: list[str] = Field(default_factory=list)

    # Similarity scores
    overall_similarity: float = Field(0.0, ge=0.0, le=1.0)
    clause_similarity: float = Field(0.0, ge=0.0, le=1.0)

    def summary(self) -> str:
        """Get a summary of the comparison."""
        total_diffs = (
            len(self.party_differences)
            + len(self.clause_differences)
            + len(self.financial_differences)
            + len(self.date_differences)
        )

        return f"""
Contract Comparison Summary
===========================
Overall Similarity: {self.overall_similarity:.2%}
Total Differences: {total_diffs}

Party Differences: {len(self.party_differences)}
Clause Differences: {len(self.clause_differences)}
Financial Differences: {len(self.financial_differences)}
Date Differences: {len(self.date_differences)}
"""
