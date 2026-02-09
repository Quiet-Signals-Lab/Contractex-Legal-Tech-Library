"""Document loaders for various file formats."""

from contractex.loaders.base import DocumentLoader
from contractex.loaders.pdf import PDFLoader
from contractex.loaders.docx import DOCXLoader
from contractex.loaders.auto import AutoLoader

__all__ = [
    "DocumentLoader",
    "PDFLoader",
    "DOCXLoader",
    "AutoLoader",
]
