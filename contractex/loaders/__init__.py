"""Document loaders for various file formats and remote sources."""

from __future__ import annotations

from contractex.loaders.auto import AutoLoader
from contractex.loaders.base import DocumentLoader
from contractex.loaders.docx import DOCXLoader
from contractex.loaders.langchain_compat import LangChainDocumentAdapter
from contractex.loaders.pdf import PDFLoader
from contractex.loaders.source_adapter import (
    APILoader,
    FetchCache,
    FetchResult,
    SourceAdapter,
    URLLoader,
)
from contractex.loaders.text import TextLoader

__all__ = [
    "DocumentLoader",
    "PDFLoader",
    "DOCXLoader",
    "TextLoader",
    "AutoLoader",
    "LangChainDocumentAdapter",
    # Network / remote sources
    "SourceAdapter",
    "URLLoader",
    "APILoader",
    "FetchCache",
    "FetchResult",
]
