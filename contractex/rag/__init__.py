"""
RAG pipeline for ContractEx.

End-to-end retrieval-augmented generation over legal document corpora.

Quick start::

    from contractex.rag import LegalRAGPipeline
    from contractex.llm.openai_provider import OpenAIProvider

    pipeline = LegalRAGPipeline(llm_provider=OpenAIProvider())
    pipeline.ingest(["contracts/msa.pdf", "statutes/gdpr.pdf"])

    response = pipeline.query("What are the data retention obligations?")
    print(response.answer)
    for citation in response.citations:
        print(citation.citation_string)
"""

from __future__ import annotations

from contractex.rag.citation import Citation, CitationFormatter
from contractex.rag.conflict import Conflict, ConflictDetector, ConflictType
from contractex.rag.pipeline import IngestResult, LegalRAGPipeline, RAGResponse, SyncResult

__all__ = [
    "LegalRAGPipeline",
    "RAGResponse",
    "IngestResult",
    "SyncResult",
    "Citation",
    "CitationFormatter",
    "Conflict",
    "ConflictType",
    "ConflictDetector",
]
