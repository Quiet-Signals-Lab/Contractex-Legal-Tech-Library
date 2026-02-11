"""Document loaders for various file formats."""

from contractex.loaders.auto import AutoLoader
from contractex.loaders.base import DocumentLoader
from contractex.loaders.docx import DOCXLoader
from contractex.loaders.langchain_compat import LangChainDocumentAdapter
from contractex.loaders.pdf import PDFLoader

__all__ = [
    "DocumentLoader",
    "PDFLoader",
    "DOCXLoader",
    "AutoLoader",
    "LangChainDocumentAdapter",
]
