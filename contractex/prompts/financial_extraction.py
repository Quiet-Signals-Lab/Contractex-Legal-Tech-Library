"""Prompt templates for financial term extraction."""

FINANCIAL_EXTRACTION_PROMPT = """
You are a financial analyst specializing in contract review. Extract all financial terms from this contract.

Contract Text:
{contract_text}

For each financial term, identify:
1. Type (payment_amount, penalty, bonus, deposit, royalty, commission, etc.)
2. Amount (numeric value)
3. Currency
4. Payment frequency (one-time, monthly, quarterly, annually, etc.)
5. Due date or payment schedule
6. Description/context
7. Any conditions that apply
8. Confidence score (0.0-1.0)

Instructions:
- Extract ALL monetary amounts, fees, payments, penalties, etc.
- Include both recurring and one-time payments
- Capture payment conditions (e.g., "net 30", "upon delivery")
- Note any variable pricing or fee structures
- Identify caps, minimums, or ranges
- Extract late payment penalties or interest rates
- Include deposits, advances, or prepayments

Common financial terms to look for:
- Base fees/service fees
- License fees
- Royalties or revenue shares
- Bonuses or incentives
- Penalties for breach or late payment
- Deposits or security amounts
- Reimbursable expenses
- Insurance requirements
- Liability caps (financial aspect)

Return as structured JSON with all amounts in decimal format.
"""


PRICING_STRUCTURE_PROMPT = """
Analyze the pricing structure and payment terms in this contract.

Contract Text:
{contract_text}

Provide analysis on:
1. Overall pricing model (fixed, variable, tiered, per-unit, etc.)
2. Total contract value (if determinable)
3. Payment schedule summary
4. Any cost escalation or adjustment clauses
5. Financial risks or unusual terms

Give a brief summary (4-5 sentences) suitable for business review.
"""
