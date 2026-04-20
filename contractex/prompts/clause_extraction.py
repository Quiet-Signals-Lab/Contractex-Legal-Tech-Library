"""Prompt templates for clause extraction."""

from __future__ import annotations

# Full CUAD taxonomy with one-line descriptions embedded in the prompt so
# that any LLM — including small local models — can pick the right category
# without needing to know the CUAD standard in advance.
_CUAD_TAXONOMY = """
CLAUSE TYPES (use the exact value in parentheses):
  - Termination for cause (termination_for_cause): Conditions allowing termination due to breach or default
  - Termination for convenience (termination_for_convenience): Right to terminate without cause
  - Notice period to terminate (notice_period_to_terminate): Required advance notice before termination
  - Payment terms (payment_terms): Payment amounts, schedules, invoicing, and net-N conditions
  - Cap on liability (cap_on_liability): Maximum aggregate liability of a party
  - Liquidated damages (liquidated_damages): Pre-agreed damages or penalties for breach
  - Price restrictions (price_restrictions): Restrictions on changing prices
  - License grant (license_grant): Grant of rights to use intellectual property
  - IP ownership / assignment (ip_ownership_assignment): Transfer of IP ownership or work-for-hire
  - Joint IP ownership (joint_ip_ownership): Shared ownership of created intellectual property
  - Non-compete (non_compete): Restriction on competing business activities
  - Exclusivity (exclusivity): Exclusive rights or sole-supplier obligations
  - No solicitation of customers (no_solicit_of_customers): Prohibition on soliciting clients
  - No solicitation of employees (no_solicit_of_employees): Prohibition on poaching staff
  - Confidentiality / NDA (confidentiality): Non-disclosure and confidentiality obligations
  - Data security (data_security): Data protection, security measures, GDPR/CCPA compliance
  - Audit rights (audit_rights): Right to inspect books, records, or systems
  - Uncapped liability (uncapped_liability): Unlimited liability exposure
  - Indemnification (indemnification): Obligation to indemnify and hold harmless
  - Insurance requirements (insurance_requirements): Required insurance coverage types and minimums
  - Warranty disclaimer (warranty_disclaimer): Disclaimer of implied or express warranties
  - Change of control (change_of_control): Provisions triggered by M&A or ownership change
  - Anti-assignment (anti_assignment): Restriction on transferring the agreement
  - Contract modification (contract_modification): How the agreement may be amended
  - Governing law (governing_law): Which jurisdiction's law controls the agreement
  - Venue (venue): Courts or forums where disputes must be resolved
  - Arbitration (arbitration): Mandatory arbitration of disputes
  - Revenue / profit sharing (revenue_profit_sharing): Revenue shares, royalties, commissions
  - Minimum commitment (minimum_commitment): Minimum purchase, volume, or spend obligations
  - Volume restriction (volume_restriction): Maximum volume or quantity limits
  - Most favoured nation (most_favored_nation): Obligation to offer best pricing to this party
  - Right of first refusal/offer/negotiation (rofr_rofo_rofn): Pre-emptive rights on transfers or deals
  - Renewal term (renewal_term): Automatic renewal conditions and notice requirements
  - Effective date (effective_date): When the agreement becomes legally operative
  - Expiration date (expiration_date): When the agreement terminates by its own terms
  - If no category fits, use: miscellaneous
"""

CLAUSE_EXTRACTION_PROMPT = (
    "You are an expert legal analyst specialising in commercial contract review.\n\n"
    "Extract every legally significant clause from the contract text below.\n\n"
    + _CUAD_TAXONOMY
    + """
INSTRUCTIONS:
- Extract ONLY substantive clauses — skip recitals (WHEREAS …), signature blocks, and table of contents entries.
- Use the exact clause_type value shown in parentheses above.
- If a clause spans multiple sub-sections, include the complete text of all sub-sections.
- If the same obligation appears in both a main clause and a cross-reference, extract it once.
- For nested clauses (e.g. a non-compete inside a termination section), extract each as a separate entry.
- Set confidence > 0.85 only when you are very certain of both the text boundary and the clause type.
- If no significant clauses are present in this excerpt, return an empty clauses list.

CONTRACT TEXT:
{contract_text}
"""
)


CONTRACT_INFO_PROMPT = """You are an expert legal analyst.

Extract the following information from the contract opening section below.

WHAT TO EXTRACT:
1. contract_type — pick the single best match from:
   nda, master_service_agreement, statement_of_work, employment_agreement,
   lease_agreement, purchase_agreement, license_agreement, partnership_agreement,
   joint_venture, franchise_agreement, distribution_agreement, reseller_agreement,
   consulting_agreement, unknown
   (use "unknown" if none fit)

2. title — the official name/title of the agreement exactly as written

3. effective_date — when the agreement becomes operative (as written, e.g. "January 1, 2024")

4. expiration_date — when the agreement ends or expires (as written)

5. signature_date — date the agreement was executed (as written)

6. governing_law — the jurisdiction whose laws govern the agreement

7. parties — ALL primary contracting parties (not third parties mentioned in passing).
   For each party:
   - name: full legal name
   - role: one of provider, client, licensor, licensee, buyer, seller,
           employer, employee, landlord, tenant, partner, other
   - entity_type: legal form (corporation, LLC, individual, partnership, …)
   - jurisdiction: state/country of incorporation if stated
   - address: registered address if stated
   - confidence: 0.0–1.0

INSTRUCTIONS:
- Return null for any field not explicitly stated in the text (do not guess).
- Extract only parties that are signatories or named as the primary counterparties.
- Do not include law firms, agents, or third parties mentioned incidentally.
- Dates should be returned exactly as written in the contract, not reformatted.

CONTRACT TEXT:
{contract_text}
"""


CLAUSE_CLASSIFICATION_PROMPT = (
    "You are a legal AI assistant specialising in contract clause classification.\n\n"
    "Classify the following contract clause according to the CUAD taxonomy.\n\n"
    + _CUAD_TAXONOMY
    + """
Clause Text:
{clause_text}

Provide:
1. The most appropriate clause_type (use the exact value in parentheses above)
2. Confidence score (0.0–1.0)
3. Brief reasoning (one sentence)
4. Up to 2 alternative types if the clause could fit multiple categories

Return as JSON.
"""
)


CLAUSE_SUMMARIZATION_PROMPT = """You are a legal document analyst. Summarise the key points of the following contract clause.

Clause Type: {clause_type}

Clause Text:
{clause_text}

Provide a concise summary (2–3 sentences) that captures:
- The main obligation or right
- Key conditions or limitations
- Any important dates, amounts, or parties mentioned

Focus on what matters most for business and legal understanding.
"""
