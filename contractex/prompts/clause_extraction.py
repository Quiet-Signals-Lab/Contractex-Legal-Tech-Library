"""Prompt templates for clause extraction."""

CLAUSE_EXTRACTION_PROMPT = """
You are an expert legal document analyst specializing in contract analysis.

Your task is to identify and extract clauses from the following contract text.

For each clause you identify:
1. Classify it according to CUAD taxonomy (e.g., termination, payment_terms, confidentiality)
2. Extract the full text of the clause
3. Note the section number if present
4. Provide a confidence score (0.0-1.0) for your classification

Contract Text:
{contract_text}

Instructions:
- Be thorough and identify all significant clauses
- Preserve the exact wording from the contract
- For multi-part clauses, extract the complete provision
- If a clause could fit multiple categories, choose the most specific one
- Provide higher confidence scores (>0.9) only when very certain

Return the analysis as structured JSON.
"""


CLAUSE_CLASSIFICATION_PROMPT = """
You are a legal AI assistant specializing in contract clause classification.

Classify the following contract clause according to the CUAD taxonomy.

Clause Text:
{clause_text}

Available Categories:
{cuad_categories}

Provide:
1. The most appropriate category
2. Confidence score (0.0-1.0)
3. Brief reasoning for your classification

If the clause could fit multiple categories, list the top 2-3 in order of relevance.
"""


CLAUSE_SUMMARIZATION_PROMPT = """
You are a legal document analyst. Summarize the key points of the following contract clause.

Clause Type: {clause_type}

Clause Text:
{clause_text}

Provide a concise summary (2-3 sentences) that captures:
- The main obligation or right
- Key conditions or limitations
- Any important dates, amounts, or parties mentioned

Focus on what matters most for business and legal understanding.
"""
