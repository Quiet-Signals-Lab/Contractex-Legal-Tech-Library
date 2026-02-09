"""Prompt templates for party extraction."""

PARTY_EXTRACTION_PROMPT = """
You are an expert legal document analyst. Extract all parties mentioned in this contract.

Contract Text:
{contract_text}

For each party, identify:
1. Legal name of the entity or person
2. Role in the contract (provider, client, licensor, licensee, etc.)
3. Entity type (corporation, LLC, individual, partnership, etc.) if mentioned
4. Jurisdiction of incorporation if mentioned
5. Any contact information or addresses
6. Confidence score (0.0-1.0) for extraction accuracy

Instructions:
- Distinguish between the primary contracting parties and other mentioned entities
- Be precise with legal names (look for "a Delaware corporation", "Inc.", "LLC", etc.)
- Extract addresses and contact info if present
- Note any parent companies or subsidiaries if relevant
- Provide high confidence (>0.9) only when information is explicitly stated

Common party roles:
- Provider/Vendor/Supplier
- Client/Customer/Buyer
- Licensor/Licensee
- Employer/Employee
- Landlord/Tenant
- Partner (in joint ventures)

Return as structured JSON.
"""


PARTY_RELATIONSHIP_PROMPT = """
Analyze the relationship between the parties in this contract.

Contract Text:
{contract_text}

Parties Identified:
{parties}

Describe:
1. Primary relationship type (B2B service, employment, partnership, etc.)
2. Power dynamics (if any party has more leverage)
3. Dependencies mentioned
4. Any parent-subsidiary or affiliate relationships

Provide a brief analysis (3-4 sentences).
"""
