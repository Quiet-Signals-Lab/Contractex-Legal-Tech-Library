"""Auto-detecting document loader."""

from pathlib import Path

from contractex.exceptions import UnsupportedFileTypeError
from contractex.loaders.base import DocumentLoader
from contractex.loaders.docx import DOCXLoader
from contractex.loaders.pdf import PDFLoader


class AutoLoader(DocumentLoader):
    """
    Auto-detecting document loader that chooses the appropriate loader
    based on file extension.
    """

    def __init__(self, **loader_kwargs):
        """
        Initialize auto loader.

        Args:
            **loader_kwargs: Keyword arguments passed to specific loaders
        """
        self.loader_kwargs = loader_kwargs

        # Initialize specific loaders
        self.loaders = {
            ".pdf": PDFLoader(**loader_kwargs),
            ".docx": DOCXLoader(**loader_kwargs),
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

        return loader.load(source)

    def get_metadata(self, source: str):
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
