"""Prompt templates for risk analysis."""

RISK_ANALYSIS_PROMPT = """
You are a seasoned contract attorney specializing in risk identification and mitigation.

Analyze the following contract for potential risks and unfavorable terms.

Contract Text:
{contract_text}

Identify risks in these categories:

1. LIABILITY RISKS:
   - Unlimited or uncapped liability
   - Broad indemnification obligations
   - Warranty disclaimers that create risk
   - Insurance gaps

2. TERMINATION RISKS:
   - Difficult termination conditions
   - Long notice periods
   - Automatic renewal without clear opt-out
   - Financial penalties for termination

3. FINANCIAL RISKS:
   - Hidden costs or fees
   - Unfavorable payment terms
   - Unilateral price increase rights
   - Excessive penalties

4. INTELLECTUAL PROPERTY RISKS:
   - Broad IP assignment
   - Loss of ownership rights
   - Restrictions on IP use
   - Patent indemnification

5. OPERATIONAL RISKS:
   - Overly restrictive non-compete
   - Exclusivity that limits business
   - Non-solicitation clauses
   - Change of control triggers

6. COMPLIANCE RISKS:
   - Data privacy obligations
   - Regulatory compliance requirements
   - Audit rights implications

7. DISPUTE RESOLUTION RISKS:
   - Unfavorable venue selection
   - Mandatory arbitration
   - Attorney fee provisions
   - Governing law issues

For each risk identified:
- Type: Category from above
- Severity: critical, high, medium, low
- Description: Clear explanation of the risk
- Clause reference: Where the risk appears
- Impact: Potential business consequences  
- Recommendation: How to mitigate or address
- Confidence: Score (0.0-1.0) for detection accuracy

Focus on risks that could have significant business or financial impact.
Prioritize critical and high-severity risks.

Return as structured JSON.
"""


RISK_COMPARISON_PROMPT = """
You are a legal advisor comparing contract terms to industry standards.

Clause Type: {clause_type}
Clause Text: {clause_text}

Compare this clause to typical market standards for {contract_type} agreements.

Assess:
1. Is this clause more favorable, standard, or unfavorable compared to market norms?
2. What specific terms deviate from standard practice?
3. What business risks does this create?
4. What would be a more balanced alternative?

Provide a brief analysis (3-4 sentences) suitable for business stakeholders.
"""


RISK_SUMMARY_PROMPT = """
Provide an executive summary of the key risks in this contract.

Contract Details:
- Type: {contract_type}
- Total Risks Identified: {risk_count}

Risks:
{risks_list}

Create an executive summary with:
1. Overall risk level (Low/Medium/High/Critical)
2. Top 3 most critical risksNumber of risks by severity
4. Key recommendations for negotiation or mitigation
5. Deal-breaker issues (if any)

Format as a concise briefing document (5-7 sentences) for executive review.
"""
