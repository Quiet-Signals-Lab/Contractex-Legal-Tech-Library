# Contract Clause Intelligence Extractor
## Revised Project Plan (February 2026)

**Version 2.0** | **Status**: Ready for Implementation

---

## Executive Summary

This project implements a production-grade, privacy-first contract analysis system that performs **structured clause extraction** from legal documents using open-source European vision-language models. Targeting 72-76% F1-score on the CUAD benchmark (510 contracts, 41 clause types), the system addresses the absence of modern, self-hosted legal extraction tools in the OSS landscape.

**Core Technical Contribution**: Combines **vision-aware chunking** with **Pydantic-structured LLM output** and **ACORD-style retrieval semantics**, enabling precise clause identification without proprietary APIs. Designed for EU legal professionals, procurement teams, and compliance officers, with full GDPR compliance via local inference.

**Novelty Assessment**: No existing OSS project integrates Llama-3.2-Vision (11B), CUAD clause taxonomy (41 types), and EuroVLM-9B multilingual capabilities in a production-ready FastAPI service.

---

## Project Scope (8-Week MVP)

### **In Scope**

1. **Document Ingestion**: PDF/DOCX/images (scanned contracts) via PyMuPDF + vision preprocessing
2. **Clause Extraction**: 25-30 high-impact CUAD clauses (prioritizing easy/medium difficulty categories)
   - Easy (>85% F1): Parties, effective date, governing law
   - Medium (70-85% F1): Limitation of liability, termination for convenience, confidentiality, indemnification
3. **Entity Recognition**: 
   - Parties with roles (vendor, client, buyer, seller)
   - Dates (effective, expiration, renewal, notice periods)
   - Financial terms (amounts, payment schedules, fees)
4. **Risk Analysis**: Detection of 10 predefined risks
   - Unlimited/uncapped liability
   - Auto-renewal without notice periods
   - Missing standard clauses
   - Overly broad non-compete provisions
5. **Data Validation**: Pydantic v2 schemas with confidence scoring (≥0.7 threshold flagged for review)
6. **Output Formats**: JSON, CSV, Excel exports with formatted tables
7. **User Interface**: Streamlit MVP featuring document viewer, clause highlighting, annotations
8. **Benchmarking**: Evaluation against CUAD test set targeting 72-76% F1-score

### **Out of Scope (Post-MVP Enhancements)**

1. ACORD retrieval integration (precedent clause search)
2. Fine-tuned models (requires >1,000 labeled contracts)
3. Multi-jurisdiction legal reasoning (Dutch/German/UK law variances)
4. Knowledge graphs for clause cross-references
5. Integration with CLM platforms (ContractSafe, Ironclad)
6. Advanced analytics dashboards

---

## Technical Architecture

### **Data Flow Pipeline**

```
Input Document (PDF/Image)
    ↓
[Vision Preprocessing - Llama-3.2-11B-Vision]
Extract text with layout awareness
    ↓
[Semantic Chunking]
500-token windows with 20% overlap, preserve clause boundaries
    ↓
[Multilingual Retrieval - sentence-transformers/multilingual-e5]
Query: "Find termination clauses" → Top-3 relevant chunks
    ↓
[Structured Extraction - Llama-3.2-90B + Instructor]
Pydantic schema validation, confidence scoring
    ↓
[Risk Analysis]
Rule-based + lightweight LLM reasoning
    ↓
[Storage & Output]
PostgreSQL persistence + JSON/CSV/Excel exports
```

### **Model Selection (EU/OSS First)**

| Model | Params | Est. F1 | Vision | Multilingual | License | Deployment |
|-------|--------|---------|--------|--------------|---------|------------|
| **Llama-3.2-90B** | 90B | 72-76% | ❌ | 8 languages | Meta | Ollama (local) ✅ |
| **Llama-3.2-11B-Vision** | 11B | N/A | ✅ | 8 languages | Meta | Ollama ✅ |
| **EuroVLM-9B** | 9B | 70-75% | ✅ | 35 EU languages | OpenRAIL | HuggingFace ✅ |
| **Qwen2.5-VL-32B** | 32B | 74-78% | ✅ | 40+ languages | Apache 2.0 | Self-hosted ✅ |

**Primary Stack**: Llama-3.2 (zero API costs, full privacy). **Fallback**: EuroVLM-9B (EU-native multilingual support).

### **Architecture Layers**

#### **Presentation Layer**
- Technology: Streamlit (MVP) → React (production)
- Features: PDF viewer, clause highlighting, inline editing, comparison view

#### **API Layer**
- Technology: FastAPI + Pydantic v2.9
- Key Endpoints:
  - `POST /api/contracts/upload` - Accept documents
  - `POST /api/contracts/analyze` - Trigger extraction
  - `GET /api/contracts/{id}/clauses` - Retrieve extracted clauses
  - `GET /api/contracts/compare` - Multi-contract comparison
  - `GET /api/contracts/{id}/export` - Export to format

#### **Processing Pipeline**
1. Document preprocessing (filetype detection, OCR for scans)
2. Vision-aware extraction (Llama-3.2-11B-Vision)
3. Semantic chunking with retrieval
4. Clause classification (25-30 CUAD types)
5. Risk assessment
6. Pydantic validation

#### **Data Layer**
- Technology: PostgreSQL (production) / SQLite (MVP)
- Tables: contracts, clauses, parties, financial_terms, risk_flags

---

## Pydantic Data Models (v2.9+)

### **Core Schemas**

```python
from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Literal
from enum import Enum
from datetime import date
from decimal import Decimal

class ClauseType(str, Enum):
    """25-30 priority CUAD clause types (MVP scope)"""
    # Easy extraction (>85% F1)
    PARTIES = "parties"
    EFFECTIVE_DATE = "effective_date"
    EXPIRATION_DATE = "expiration_date"
    GOVERNING_LAW = "governing_law"
    NOTICE_PERIOD = "notice_period_to_terminate"
    
    # Medium extraction (70-85% F1)
    LIMITATION_OF_LIABILITY = "cap_on_liability"
    UNCAPPED_LIABILITY = "uncapped_liability"
    TERMINATION_FOR_CONVENIENCE = "termination_for_convenience"
    CONFIDENTIALITY = "confidentiality"
    INDEMNIFICATION = "indemnification"
    NON_COMPETE = "non_compete"
    IP_OWNERSHIP = "ip_ownership_assignment"
    WARRANTY_DURATION = "warranty_duration"
    FORCE_MAJEURE = "force_majeure"
    
    # Additional medium types
    RENEWAL_TERM = "renewal_term"
    CHANGE_OF_CONTROL = "change_of_control"
    DISPUTE_RESOLUTION = "dispute_resolution"
    ARBITRATION = "arbitration"
    ASSIGNMENT = "anti_assignment"
    NON_SOLICITATION = "non_solicitation_of_customers"
    MOST_FAVORED_NATION = "most_favored_nation"
    AUDIT_RIGHTS = "audit_rights"

class RiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ContractClause(BaseModel):
    """Extracted clause with metadata and risk assessment"""
    clause_type: ClauseType
    text_span: str = Field(
        ..., 
        description="Full verbatim text of clause from contract"
    )
    page_number: Optional[int] = Field(
        default=None,
        description="Page where clause appears"
    )
    section_reference: Optional[str] = Field(
        default=None,
        description="Section number or heading (e.g., '3.2 Liability')"
    )
    confidence: Decimal = Field(
        ...,
        ge=Decimal("0.0"),
        le=Decimal("1.0"),
        description="LLM confidence score (0.0-1.0)"
    )
    risk_level: RiskLevel = Field(
        default=RiskLevel.NONE,
        description="Risk assessment of this clause"
    )
    is_standard: bool = Field(
        default=True,
        description="Whether this is a standard clause for contract type"
    )
    risk_explanation: Optional[str] = Field(
        default=None,
        description="Why this clause poses risk (if risk_level > NONE)"
    )

class Party(BaseModel):
    """Contracting party with role and legal entity details"""
    name: str = Field(..., description="Legal name as stated in contract")
    role: Literal[
        "vendor", "client", "buyer", "seller", 
        "employer", "employee", "licensor", "licensee"
    ]
    legal_entity_type: Optional[Literal[
        "corporation", "LLC", "partnership", 
        "individual", "government", "nonprofit"
    ]] = None
    address: Optional[str] = None
    jurisdiction: Optional[str] = None

class FinancialTerm(BaseModel):
    """Extracted payment term or financial obligation"""
    term_type: Literal[
        "payment", "fee", "penalty", "deposit", 
        "bonus", "commission", "minimum_commitment"
    ]
    amount: Decimal = Field(..., gt=0)
    currency: str = Field(default="EUR")
    frequency: Literal[
        "one-time", "monthly", "quarterly", "annually", "upon_milestone"
    ]
    description: str
    due_date: Optional[date] = None

class RiskFlag(BaseModel):
    """Identified risk or issue requiring attention"""
    risk_type: Literal[
        "missing_clause", "unlimited_liability", 
        "auto_renewal_trap", "unusual_term", "ambiguous_language"
    ]
    severity: RiskLevel
    description: str = Field(
        ...,
        description="Clear explanation of the risk"
    )
    recommendation: str = Field(
        ...,
        description="Suggested action or mitigation"
    )
    clause_reference: Optional[str] = None
    page_number: Optional[int] = None

class ContractData(BaseModel):
    """Complete extracted contract structure"""
    contract_id: str
    contract_type: Optional[str] = Field(
        default=None,
        description="NDA, MSA, SOW, employment, etc."
    )
    parties: List[Party] = Field(
        ...,
        min_items=2,
        description="Minimum two contracting parties"
    )
    effective_date: Optional[date] = None
    expiration_date: Optional[date] = None
    clauses: List[ContractClause]
    financial_terms: Optional[List[FinancialTerm]] = None
    risk_flags: List[RiskFlag] = Field(
        default_factory=list,
        description="Identified risks and issues"
    )
    overall_confidence: Decimal = Field(
        ...,
        ge=Decimal("0.0"),
        le=Decimal("1.0"),
        description="Average confidence across all extractions"
    )
    
    @field_validator("expiration_date")
    @classmethod
    def validate_date_order(cls, v: Optional[date], info) -> Optional[date]:
        if v and info.data.get("effective_date"):
            if v <= info.data["effective_date"]:
                raise ValueError("Expiration date must be after effective date")
        return v
```

### **Validation Strategy**

- **Schema Enforcement**: Pydantic validates all fields before storage
- **Confidence Threshold**: Flag extractions with confidence < 0.7 for human review
- **Cross-validation**: Verify effective_date < expiration_date, parties >= 2
- **Deduplication**: Detect and merge duplicate clause extractions

---

## LLM Integration Strategy

### **Chunking & Retrieval** (Inspired by ACORD Best Practices)

**Rationale**: Full-document context causes token explosion and quality degradation. Targeted retrieval reduces tokens by 60% and improves F1 by ~5%.

```python
def intelligent_chunking(document_text: str, chunk_size: int = 500):
    """
    Semantic chunking preserving clause boundaries
    - Chunk size: 500 tokens (CUAD optimal)
    - Overlap: 20% (preserve context)
    - Split points: Section headers, paragraph breaks
    """
    # Use recursive character splitter with legal-aware separators
    separators = [
        "\n\n## ",  # Major section breaks
        "\n\n",     # Paragraph breaks
        "\n",       # Line breaks
        ". ",       # Sentence breaks
        " "         # Words (last resort)
    ]
    # Add metadata: page_number, section_title
    return chunks_with_metadata

def retrieve_relevant_chunks(
    contract_chunks: List[str],
    clause_type: ClauseType,
    embedding_model: str = "sentence-transformers/multilingual-e5-large"
) -> List[str]:
    """
    Retrieve top-3 most relevant chunks for specific clause type
    Query: "Extract {clause_type} clauses"
    """
    # Embed chunks and query
    # Return top-3 by cosine similarity
    pass
```

### **Extraction Pipeline**

```python
async def extract_clauses(
    document: bytes,
    clause_types: List[ClauseType] = None
) -> ContractData:
    """
    End-to-end extraction with structured output
    """
    # 1. Preprocess document
    text, metadata = await preprocess_document(document)
    
    # 2. Create chunks with retrieval
    chunks = intelligent_chunking(text)
    embeddings = embed_chunks(chunks)  # multilingual-e5
    
    # 3. For each CUAD type, extract via LLM
    extracted_clauses = []
    for clause_type in clause_types or ClauseType:
        query = f"Extract {clause_type} clauses with legal precision"
        relevant_chunks = retrieve_relevant_chunks(
            chunks, clause_type, embeddings
        )
        
        # Use Instructor library for Pydantic output
        clause = await llm_extract_clause(
            relevant_chunks,
            clause_type,
            output_model=ContractClause
        )
        extracted_clauses.append(clause)
    
    # 4. Analyze risks
    risk_flags = analyze_risks(extracted_clauses)
    
    # 5. Validate and return
    contract_data = ContractData(
        contract_id=metadata["id"],
        parties=...,
        clauses=extracted_clauses,
        risk_flags=risk_flags,
        overall_confidence=calculate_confidence(extracted_clauses)
    )
    return contract_data
```

### **Prompt Template**

```
You are an expert legal contract analyst specializing in commercial agreements.

Extract the following clause type from the contract excerpt:
CLAUSE_TYPE: {clause_type}

CLAUSE DEFINITION: {definition_from_CUAD}

CONTRACT EXCERPT:
{retrieved_chunks}

INSTRUCTIONS:
1. Identify if this clause exists in the excerpt
2. Extract the complete clause text (verbatim)
3. Assess risk level (none/low/medium/high/critical)
4. Rate your confidence (0.0-1.0)
5. Note page number and section reference
6. Flag if non-standard for this contract type

Return as valid JSON matching ContractClause schema.
Confidence score reflects legal precision, not guessing.
If clause not found, explicitly state "NOT_FOUND".
```

### **Error Handling & Robustness**

1. **Confidence Thresholds**: Extractions < 0.7 confidence flagged for human review
2. **Validation Errors**: If Pydantic fails, retry with clarification prompt
3. **Fallback Chain**: Llama-3.2-90B → Qwen2.5-VL-32B → Manual review queue
4. **Cost Control**: Token budget tracking, batch processing optimization
5. **Rate Limiting**: Exponential backoff for API calls

---

## CUAD Clause Taxonomy (MVP Focus: 25-30 Types)

### **Priority Tiers**

**Tier 1 - Easy (>85% F1)**: 8 clauses
- Parties, effective date, expiration date, governing law, notice period, renewal term, termination for convenience, change of control

**Tier 2 - Medium (70-85% F1)**: 17 clauses
- Limitation/uncapped liability, confidentiality, indemnification, non-compete, IP ownership, warranty duration, force majeure, assignment, non-solicitation, most favored nation, audit rights, dispute resolution, arbitration, minimum commitment, payment terms, liquidated damages, auto-renewal

**Tier 3 - Hard (<70% F1)** - Post-MVP
- Definitions (cross-references), conditional logic, revenue sharing, source code escrow

---

## Implementation Roadmap (8 Weeks)

### **Weeks 1-2: Foundation & Data Preparation**

**Deliverables**:
- Project repository with Git structure
- All Pydantic v2 schemas implemented and unit-tested
- CUAD dataset downloaded and evaluation split prepared
- FastAPI project skeleton with basic auth
- PostgreSQL schema designed and migrated

**Key Tasks**:
```
1. Clone repo, set up virtual environment
2. pip install -r requirements.txt
3. Define 25-30 ClauseType enums
4. Create Pydantic models for ContractData, Party, Clause, RiskFlag
5. Test schema validation with mock data
6. Download CUAD dataset (510 contracts)
7. Create evaluation pipeline: precision, recall, F1 per clause type
8. Set up PostgreSQL with SQLAlchemy ORM
```

**Definition of Done**:
- All schemas pass validation tests
- Evaluation script runs on CUAD dataset
- FastAPI `/health` endpoint responds

### **Weeks 3-5: Core Extraction Pipeline**

**Deliverables**:
- Llama-3.2-90B integration via Ollama
- Chunking + retrieval system operational
- Clause extraction on 10 sample contracts
- Risk analysis engine functional
- 70%+ F1 on easy clause types

**Key Tasks**:
```
1. Install Ollama, download Llama-3.2-90B + 11B-Vision
2. Implement intelligent_chunking() with clause boundary preservation
3. Set up sentence-transformers/multilingual-e5 for embeddings
4. Implement retrieve_relevant_chunks() with top-3 selection
5. Create extract_clauses() with Instructor library
6. Write risk_analysis_engine() for 10 predefined risks
7. Test end-to-end on 10 contracts from CUAD
8. Measure F1 per clause type, identify failure modes
```

**Evaluation Milestones**:
- Easy clauses (parties, dates): ≥85% F1
- Medium clauses (liability, termination): 70-80% F1

### **Weeks 6-7: UI, Export, Validation**

**Deliverables**:
- Streamlit MVP with document viewer
- JSON/CSV/Excel export functionality
- Confidence scoring visualization
- Clause comparison tables
- Full CUAD test set evaluation

**Key Tasks**:
```
1. Build Streamlit UI:
   - File upload with drag-drop
   - PDF viewer with page navigation
   - Extracted clauses with highlighting
   - Risk flags with severity badges
   - Edit/correct interface
2. Implement export_to_json(), export_to_csv(), export_to_excel()
3. Add confidence score percentiles and warnings
4. Build multi-contract comparison view
5. Run full evaluation on CUAD test set (50 contracts)
6. Generate precision/recall/F1 report
7. Document edge cases and error patterns
```

**Target Metrics**:
- Overall F1: 72-76% (target)
- Precision@80% Recall (legal standard)
- Processing time: <10 seconds/page

### **Week 8: Documentation, Demo, Deployment**

**Deliverables**:
- Comprehensive GitHub README
- Demo video (3-4 minutes)
- Docker configuration
- Deployment documentation
- Upwork service listing

**Key Tasks**:
```
1. Write GitHub README:
   - Problem statement
   - Architecture diagram
   - Features + screenshots
   - CUAD taxonomy reference
   - Installation instructions
   - API documentation
   - Accuracy metrics on CUAD
2. Create demo video:
   - Show sample contract upload
   - Highlight real-time extraction
   - Display risk flags
   - Show multi-contract comparison
   - Export to Excel
3. Dockerize project (Dockerfile + docker-compose.yml)
4. Write deployment guide (local Ollama, cloud options)
5. Create Upwork service description
6. List on GitHub with portfolio link
```

---

## Evaluation Methodology

### **Benchmark: CUAD Test Set**

- **Dataset**: 50 contracts (held-out from 510)
- **Metrics**: 
  - Macro-averaged F1 across 25-30 clause types
  - Precision @ 80% Recall (legal industry standard)
  - Error rate per clause type
  - Confidence calibration (are 0.9-confidence predictions actually 90% correct?)

### **Real-World Testing**

**Contract Corpus** (20-30 diverse examples):
- NDAs (non-disclosure agreements)
- MSAs (master service agreements)
- SOWs (statements of work)
- Employment contracts
- Vendor/procurement agreements
- SaaS subscription terms
- Lease agreements

**Evaluation Protocol**:
- Manual annotation by domain expert
- Compute precision/recall vs ground truth
- Identify systematic failure modes
- Document edge cases (handwritten signatures, poor scans, 100-page contracts)

### **Success Criteria**

| Metric | Target | Rationale |
|--------|--------|-----------|
| **F1 Score** | 72-76% | Competitive with Llama-3.2 on CUAD |
| **Precision** | ≥80% | Legal domain requires high precision |
| **Easy Clauses** | ≥85% F1 | Parties, dates must be near-perfect |
| **Processing Time** | <10 sec/page | MVP performance acceptable |
| **Uptime** | 99%+ | Production reliability |

---

## Key Technical Considerations

### **1. Legal Domain Complexity**

**Challenges**:
- Formal language with defined terms (interdependencies)
- Clauses reference other sections (context dependent)
- Multi-label classification (single clause may fit multiple CUAD types)
- Ambiguous drafting (legal terms can have multiple interpretations)
- Jurisdiction variance (US law dominates CUAD; European contracts differ)

**Mitigations**:
- Use context-aware chunking (preserve section references)
- Support multi-label classification via `List[ClauseType]`
- Flag ambiguous extractions for human review (confidence < 0.7)
- Document jurisdiction-specific rules (post-MVP)

### **2. Accuracy Requirements**

**Legal Implications**: Missed clauses or misclassifications have real business consequences (missed liability limits, termination terms, IP ownership).

**Approach**:
- Confidence scoring on every extraction
- Human-in-the-loop verification UI
- Audit trail of all corrections
- Conservative error handling (flag uncertainty, don't guess)

**Target Accuracy**:
- Party extraction: 98% (straightforward NER)
- Date extraction: 95% (format normalization)
- Clause classification: 72-76% (complex semantic task)
- Risk detection: 85% (domain knowledge)

### **3. Cost & Efficiency**

**Token Economics**:
- Average contract: 15,000 input tokens, 3,000 output tokens
- Llama-3.2 local: €0.00 per contract (no API)
- vs GPT-4o: €0.50 per contract
- vs Azure specialized: €0.50+ per contract

**Optimization**:
- Retrieval reduces tokens by 60% vs full-context
- Batch processing for high-volume users
- Caching for duplicate contracts

### **4. Privacy & Compliance**

**Requirements**:
- GDPR compliance (EU data protection)
- Legal privilege (contracts are confidential)
- Data retention (clients own extracted data)
- Encryption (at rest + in transit)

**Implementation**:
- Local Ollama inference (data never leaves user's machine)
- Optional PostgreSQL on client infrastructure
- Docker deployment for air-gapped environments
- Clear data deletion policy

### **5. Vision & OCR**

**Challenges**:
- Scanned contracts (poor quality, handwriting)
- Multi-page documents (table of contents, page breaks)
- Complex layouts (columns, embedded images)
- Redacted sections

**Handling**:
- Llama-3.2-11B-Vision for initial preprocessing
- Tesseract OCR fallback (open-source)
- Layout preservation (mark redacted sections)
- Table detection (preserve structure for financial schedules)

---

## Error Patterns & Failure Modes

**From Recent Benchmarks** [web:140][web:143]:

| Error Type | Frequency | Mitigation |
|-----------|-----------|-----------|
| **Hallucination** | 10-15% | Pydantic validation, confidence thresholds |
| **Partial extraction** | 8-12% | Retrieval + context expansion |
| **Jurisdiction confusion** | 5-8% | Include jurisdiction in prompt |
| **Nested clause misclassification** | 12-15% | Support multi-label, hierarchical structure |
| **False positives** | 10% | Require explicit mention in text_span |

---

## Testing Strategy

### **Unit Tests**

- Pydantic schemas with valid/invalid data
- Date parsing (multiple formats)
- Currency normalization
- Clause type validation
- Risk severity assignment

### **Integration Tests**

- End-to-end pipeline with 5 sample contracts
- Database CRUD operations
- API endpoint responses
- Export format correctness

### **Accuracy Benchmarking**

- CUAD test set (50 contracts)
- Precision, recall, F1 per clause type
- Confusion matrix for misclassifications
- Error analysis by contract type

---

## Deployment Architecture

### **MVP (Local Development)**

```bash
# Environment
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Ollama setup
ollama pull llama2:90b
ollama pull llama2:11b-vision

# Database
pip install postgres
createdb contract_extractor

# Run
uvicorn main:app --reload
streamlit run ui.py
```

### **Production (Docker)**

```dockerfile
FROM python:3.11-slim

# Install Ollama
RUN curl https://ollama.ai/install.sh | sh

# Copy code + requirements
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt

# Models
RUN ollama pull llama2:90b

# Run
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### **Scaling Options (Post-MVP)**

- Multi-GPU inference (multiple Ollama instances)
- PostgreSQL replication + read replicas
- FastAPI worker pool for parallel processing
- Redis caching for embeddings

---

## Competitive Analysis & Market Position

### **Market Size**

- AI Contract Review: $4.6B (2025) → $15.3B (2032), 23.6% CAGR
- Legal Tech segment underserved for OSS/self-hosted solutions

### **Competitive Landscape**

| Competitor | Type | Pricing | Limitation |
|------------|------|---------|-----------|
| **Legartis** | SaaS | €10k+/year | Proprietary, no local |
| **Ironclad** | SaaS | Custom pricing | Enterprise only |
| **Azure Content Understanding** | Proprietary | €0.50/contract | US-hosted, vendor lock-in |
| **InvoiceNet** | OSS (2019) | Free | Outdated, no legal domain |
| **invoice2data** | OSS | Free | Regex-based, no vision |

### **Your Advantages**

1. **Privacy-First**: Local Ollama (no data leakage)
2. **EU/OSS**: EuroVLM-9B + Llama stack
3. **Legal Domain**: CUAD taxonomy (41 clause types)
4. **Structured Output**: Pydantic schemas (no hallucination)
5. **Cost**: €0/contract (local) vs €0.50+ (competitors)
6. **Customizable**: Client-specific clauses, risk rules

---

## Upwork Positioning

### **Service Title**
"Contract Intelligence Extractor - Custom Build | AI-Powered Legal Document Analysis"

### **Service Description**

> "I build production-grade contract analysis systems for legal teams, procurement departments, and M&A firms. This is not a chatbot—it's a targeted extraction pipeline that transforms unstructured contracts into structured, actionable intelligence.
>
> **What You Get:**
> - Clause extraction (41 CUAD types + custom)
> - Risk flagging (unlimited liability, auto-renewal traps)
> - Party/date/financial term extraction
> - Multi-contract comparison
> - JSON/CSV/Excel exports
> - Fully customizable risk rules
>
> **My Edge:**
> - 72-76% F1 on CUAD benchmark
> - Privacy-first (local deployment)
> - EU-compliant (GDPR-safe)
> - API-first architecture
>
> **Tech Stack:**
> FastAPI, Pydantic, Llama-3.2, LangChain, PostgreSQL
>
> **Portfolio:** [Link to GitHub repo with demo video]"

### **Pricing**

| Service | Cost | Timeline |
|---------|------|----------|
| **MVP Build** | €2,000-3,500 | 6-8 weeks |
| **Custom Implementation** | €4,000-8,000 | 8-12 weeks with integrations |
| **Per-Document Processing** | €10-25 | Per-contract option |
| **Ongoing Support** | €50-75/hour | Maintenance + enhancements |

### **Ideal Clients**

- Legal tech startups
- Law firm document automation
- M&A due diligence teams
- Procurement automation
- Contract lifecycle management (non-vendor-locked)

---

## Success Metrics

### **Technical**

- F1-score: 72-76% on CUAD
- Processing time: <10 seconds/page
- Uptime: 99%+
- Confidence calibration: Predictions at 0.8 confidence are ≥75% accurate

### **Business**

- Time savings: 70-80% reduction vs manual review
- Risk detection: Identify 85%+ of high-severity clauses
- User satisfaction: Positive feedback from legal professionals
- Portfolio impact: Demonstrates sophisticated LLM application
- Revenue potential: €5k-50k/year on Upwork

---

## Timeline Summary

| Phase | Duration | Key Deliverable | Status |
|-------|----------|-----------------|--------|
| **Foundation** | Weeks 1-2 | Pydantic schemas, CUAD setup | Ready |
| **Extraction** | Weeks 3-5 | Llama-3.2 integration, 70% F1 | Planned |
| **UI & Export** | Weeks 6-7 | Streamlit MVP, full evaluation | Planned |
| **Deployment** | Week 8 | Docker, docs, Upwork launch | Planned |

---

## Resources & References

### **Datasets & Benchmarks**

- CUAD (2021): Contract Understanding Atticus Dataset, 510 contracts
- ACORD (2025): Expert-annotated retrieval dataset, 126k query-clause pairs
- ContractEval (2024): Clause-level LLM benchmarks

### **Key Papers**

- "CUAD: An Expert-Annotated NLP Dataset for Legal Contract Review" (2021) - Hendrycks et al.
- "ACORD: An Expert-Annotated Retrieval Dataset for Legal Contract Understanding" (2025)
- "Information Extraction from Contracts Using Large Language Models" (2024)

### **Tools & Libraries**

- Llama-3.2 family: https://ollama.ai
- EuroVLM: https://huggingface.co/Unbabel/EuroVLM-9B
- Sentence-transformers: https://www.sbert.net
- FastAPI: https://fastapi.tiangolo.com
- Pydantic: https://docs.pydantic.dev
- LangChain: https://python.langchain.com

### **Regulatory & Standards**

- EU GDPR compliance requirements
- Legal document best practices
- IACCM contract standards

---

## Disclaimer & Ethical Considerations

**Legal Liability**: This tool assists contract review but does not replace professional legal counsel. All extractions must be verified by qualified legal professionals.

**Accuracy Limitations**: LLMs may miss nuances, misclassify clauses, or hallucinate information. Confidence scores indicate uncertainty; flag all extractions < 0.7 for manual review.

**Jurisdiction Specificity**: CUAD training data skews toward US contract law. European, Asian, and specialized contracts may perform differently.

**Data Privacy**: Users are responsible for ensuring tool use complies with client confidentiality agreements, attorney-client privilege, and data protection regulations.

---

## Appendix A: CUAD 41 Clause Types (Complete Reference)

### **Document-Level Metadata (8)**
1. Contract type identification
2. Parties and roles
3. Effective date
4. Expiration date
5. Renewal/extension terms
6. Notice period to terminate
7. Governing law/jurisdiction
8. Dispute resolution

### **Rights & Licenses (6)**
9. License grant
10. Non-transferable license
11. Affiliate license (licensor side)
12. Affiliate license (licensee side)
13. Unlimited/all-you-can-eat license
14. Irrevocable/perpetual license

### **Restrictions (9)**
15. Non-compete
16. Exclusivity
17. Non-disparagement
18. Anti-assignment
19. Non-solicitation of customers
20. Non-solicitation of employees
21. Competitive restriction exception
22. IP ownership/assignment
23. Joint IP ownership

### **Liability & Indemnification (5)**
24. Cap on liability
25. Uncapped liability
26. Liquidated damages
27. Warranty duration
28. Covenant not to sue

### **Financial Terms (6)**
29. Minimum commitment
30. Most favored nation
31. Price restrictions
32. Revenue/profit sharing
33. Volume restriction
34. Payment terms (custom)

### **Audit & Compliance (3)**
35. Audit rights
36. Data protection/privacy
37. Third-party beneficiary

### **Termination & Post-Termination (2)**
38. Change of control
39. Termination for convenience
40. Post-termination services

### **Other (1)**
41. Right of first refusal / offer

---

## Appendix B: Quick Start Guide

```bash
# Clone repository
git clone https://github.com/yourusername/contract-clause-extractor.git
cd contract-clause-extractor

# Setup
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Pull models
ollama pull llama2:90b
ollama pull llama2:11b-vision

# Database setup
pip install psycopg2-binary
createdb contract_extractor
alembic upgrade head

# Run
uvicorn main:app --reload &
streamlit run ui.py

# Evaluate on CUAD
python evaluate.py --dataset cuad --model llama-3.2-90b
```

---

## Version History

- **v2.0** (Feb 3, 2026): Revised plan incorporating ACORD retrieval, EuroVLM-9B, Llama-3.2 stack, research-backed accuracy targets
- **v1.0** (Feb 1, 2026): Initial project outline

---

**Project Status**: Ready for Implementation  
**Last Updated**: February 3, 2026  
**Author**: Data Science Engineer  
**Repository**: [GitHub link - to be created]