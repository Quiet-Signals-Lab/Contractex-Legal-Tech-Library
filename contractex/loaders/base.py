"""Abstract base class for document loaders."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class DocumentLoader(ABC):
    """Abstract base class for document loaders."""

    @abstractmethod
    def load(self, source: str) -> str:
        """
        Load a document and return its text content.

        Args:
            source: Path to the document or other source identifier

        Returns:
            Extracted text content

        Raises:
            DocumentLoadError: If loading fails
        """
        pass

    def load_with_metadata(self, source: str) -> dict[str, Any]:
        """
        Load a document and return text with metadata.

        Args:
            source: Path to the document

        Returns:
            Dictionary with 'text' and 'metadata' keys
        """
        text = self.load(source)
        metadata = self.get_metadata(source)

        return {
            'text': text,
            'metadata': metadata,
        }

    def get_metadata(self, source: str) -> dict[str, Any]:
        """
        Get metadata about the document.

        Args:
            source: Path to the document

        Returns:
            Dictionary of metadata
        """
        path = Path(source)

        return {
            'filename': path.name,
            'file_type': path.suffix[1:],
            'file_size_bytes': path.stat().st_size if path.exists() else None,
        }

    def supports(self, file_path: str) -> bool:
        """
        Check if this loader supports the given file type.

        Args:
            file_path: Path to check

        Returns:
            True if this loader can handle the file
        """
        return True
