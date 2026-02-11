"""
LangChain Integration Example

Shows how to use ContractEx with LangChain components.

Requires optional dependencies:
    pip install langchain langchain-openai langchain-community
"""

# Example 1: Use LangChain LLM with ContractEx
from langchain_openai import ChatOpenAI  # type: ignore[import-not-found]

from contractex import ContractExtractor
from contractex.llm import LangChainProvider
from contractex.loaders import LangChainDocumentAdapter

langchain_llm = ChatOpenAI(  # type: ignore[call-arg]
    model="gpt-4o",
    temperature=0.0
)

# Wrap LangChain LLM for ContractEx
llm_provider = LangChainProvider(langchain_llm)

# Example 2: Use LangChain document loader
from langchain_community.document_loaders import PyPDFLoader  # type: ignore[import-not-found]

langchain_loader = PyPDFLoader("contract.pdf")
document_loader = LangChainDocumentAdapter(langchain_loader)

# Create extractor with LangChain components
extractor = ContractExtractor(
    llm_provider=llm_provider,
    document_loader=document_loader
)

# Extract as normal
contract = extractor.extract("contract.pdf")

print("Extracted contract using LangChain components:")
print(f"  Type: {contract.contract_type}")
print(f"  Parties: {len(contract.parties)}")
print(f"  Clauses: {len(contract.clauses)}")

# Example 3: Use ContractEx output with LangChain chains
from langchain.chains import LLMChain  # type: ignore[import-not-found]
from langchain.prompts import PromptTemplate  # type: ignore[import-not-found]

# Create a chain that uses extracted contract data
summary_template = """
Based on the following contract information, provide a brief executive summary:

Contract Type: {contract_type}
Parties: {parties}
Key Clauses: {clauses}
Identified Risks: {risks}

Provide a 3-paragraph executive summary suitable for business stakeholders.
"""

prompt = PromptTemplate(
    input_variables=["contract_type", "parties", "clauses", "risks"],
    template=summary_template
)

chain = LLMChain(llm=langchain_llm, prompt=prompt)

# Run chain with ContractEx data
summary = chain.run(
    contract_type=str(contract.contract_type),
    parties=", ".join([p.name for p in contract.parties]),
    clauses=", ".join([c.clause_type for c in contract.clauses[:10]]),
    risks=", ".join([r.risk_type for r in contract.risks])
)

print("\n=== Executive Summary ===")
print(summary)
