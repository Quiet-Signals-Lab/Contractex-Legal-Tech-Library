"""Prompt templates for party extraction."""

from __future__ import annotations

PARTY_EXTRACTION_PROMPT = """You are an expert legal document analyst. Extract all primary contracting parties from this contract.

Contract Text:
{contract_text}

For each PRIMARY party (signatories and named counterparties only), identify:
1. name: Full legal name of the entity or person
2. role: Must be exactly one of: provider, client, licensor, licensee, buyer, seller,
         employer, employee, landlord, tenant, partner, other
3. entity_type: Legal form if stated (e.g. corporation, LLC, limited partnership, individual)
4. jurisdiction: State or country of incorporation if stated (e.g. "Delaware", "England and Wales")
5. address: Physical or registered address if stated
6. confidence: 0.0–1.0 (use > 0.9 only when information is explicitly stated)

INSTRUCTIONS:
- Include ONLY the primary contracting parties — the entities that sign this agreement.
- Exclude: law firms, agents, banks, third-party beneficiaries, and entities mentioned only in examples.
- Be precise with legal names — include suffixes (Inc., LLC, Ltd., Corp.) exactly as written.
- If a party is described as "a Delaware corporation", set jurisdiction to "Delaware".
- Do not guess or infer information that is not explicitly stated; use null for missing fields.

Return as structured JSON.
"""


PARTY_RELATIONSHIP_PROMPT = """Analyse the relationship between the parties in this contract.

Contract Text:
{contract_text}

Parties Identified:
{parties}

Describe:
1. Primary relationship type (B2B service, employment, partnership, etc.)
2. Power dynamics (if any party has more leverage)
3. Dependencies mentioned
4. Any parent-subsidiary or affiliate relationships

Provide a brief analysis (3–4 sentences).
"""
