"""Auto-detecting document loader."""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any

from contractex.exceptions import UnsupportedFileTypeError
from contractex.loaders.base import DocumentLoader
from contractex.loaders.docx import DOCXLoader
from contractex.loaders.pdf import PDFLoader
from contractex.loaders.text import TextLoader


class AutoLoader(DocumentLoader):
    """
    Auto-detecting document loader that chooses the appropriate loader
    based on file extension.
    """

    def __init__(self, **loader_kwargs: Any) -> None:
        """
        Initialize auto loader.

        Args:
            **loader_kwargs: Keyword arguments for the specific loaders; each
                loader receives the ones its constructor accepts
                (e.g. ``ocr_enabled`` goes to the PDF loader only)

        Raises:
            TypeError: If no loader accepts one of the keyword arguments
        """
        self.loader_kwargs = loader_kwargs

        loader_types: dict[str, type[DocumentLoader]] = {
            ".pdf": PDFLoader,
            ".docx": DOCXLoader,
            ".txt": TextLoader,
        }
        accepted = {
            ext: set(inspect.signature(cls.__init__).parameters) & set(loader_kwargs)
            for ext, cls in loader_types.items()
        }
        unknown = set(loader_kwargs) - set().union(*accepted.values())
        if unknown:
            raise TypeError(
                f"AutoLoader got unexpected keyword argument(s): {', '.join(sorted(unknown))}"
            )

        # Initialize specific loaders
        self.loaders: dict[str, DocumentLoader] = {
            ext: cls(**{name: loader_kwargs[name] for name in accepted[ext]})
            for ext, cls in loader_types.items()
        }

    def load(self, source: str) -> str:
        """
        Auto-detect file type and load document.

        Args:
            source: Path to document

        Returns:
            Extracted text content

        Raises:
            UnsupportedFileTypeError: If file type is not supported
            DocumentLoadError: If loading fails
        """
        path = Path(source)
        extension = path.suffix.lower()

        # Get appropriate loader
        loader = self.loaders.get(extension)

        if loader is None:
            raise UnsupportedFileTypeError(
                f"Unsupported file type: {extension}. "
                f"Supported types: {', '.join(self.loaders.keys())}"
            )

        result: str = loader.load(source)
        return result

    def get_metadata(self, source: str) -> dict[str, Any]:
        """Get metadata using appropriate loader."""
        path = Path(source)
        extension = path.suffix.lower()

        loader = self.loaders.get(extension)

        if loader:
            return loader.get_metadata(source)
        else:
            return super().get_metadata(source)

    def supports(self, file_path: str) -> bool:
        """Check if any loader supports this file."""
        extension = Path(file_path).suffix.lower()
        return extension in self.loaders
