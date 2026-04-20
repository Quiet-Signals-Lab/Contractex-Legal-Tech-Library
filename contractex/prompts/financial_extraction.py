"""Prompt templates for financial term extraction."""

from __future__ import annotations

FINANCIAL_EXTRACTION_PROMPT = """You are a financial analyst specialising in contract review. Extract all financial terms from this contract section.

Contract Text:
{contract_text}

For each financial term identify:
1. term_type: Category — use one of: payment_amount, service_fee, license_fee, royalty, commission,
   bonus, penalty, deposit, reimbursement, insurance_minimum, liability_cap, late_payment_interest,
   minimum_commitment, revenue_share, or a short descriptive label if none fit
2. amount: Numeric amount as a plain string WITHOUT commas or currency symbols
   (e.g. "50000.00" or "1500" — NOT "$50,000" or "fifty thousand"). Null if variable or not stated.
3. currency: ISO 4217 code (e.g. "USD", "EUR", "GBP"). Default: "USD"
4. frequency: Must be exactly one of: one-time, monthly, quarterly, annually, weekly, per-use, or null
5. due_date: Due date or payment trigger as written (e.g. "net 30", "upon delivery", "2024-03-31")
6. description: Brief plain-English description of what this term covers
7. conditions: List of conditions or triggers that apply (e.g. ["if late payment", "upon acceptance"])
8. confidence: 0.0–1.0

INSTRUCTIONS:
- Extract ALL monetary obligations: fees, payments, penalties, royalties, deposits, insurance minimums.
- Include both recurring and one-time payments.
- For ranges (e.g. "$100–$200"), use the lower bound as amount and note the range in description.
- For percentage-based amounts (e.g. "15% of revenue"), set amount to null and describe in description.
- For liability caps, record the cap amount as a financial term with term_type "liability_cap".
- If no financial terms are present in this section, return an empty financial_terms list.

Return as structured JSON with amounts as plain numeric strings.
"""


PRICING_STRUCTURE_PROMPT = """Analyse the pricing structure and payment terms in this contract.

Contract Text:
{contract_text}

Provide analysis on:
1. Overall pricing model (fixed, variable, tiered, per-unit, etc.)
2. Total contract value (if determinable)
3. Payment schedule summary
4. Any cost escalation or adjustment clauses
5. Financial risks or unusual terms

Give a brief summary (4–5 sentences) suitable for business review.
"""
