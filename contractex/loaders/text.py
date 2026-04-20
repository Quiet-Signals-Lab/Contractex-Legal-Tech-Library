"""Plain text document loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contractex.exceptions import DocumentLoadError
from contractex.loaders.base import DocumentLoader


class TextLoader(DocumentLoader):
    """
    Plain text document loader.

    Loads .txt files directly as-is. Useful for testing and
    contracts already extracted from other sources.
    """

    def __init__(self, encoding: str = "utf-8"):
        """
        Initialize text loader.

        Args:
            encoding: Text file encoding (default: utf-8)
        """
        self.encoding = encoding

    def load(self, source: str) -> str:
        """
        Load plain text file.

        Args:
            source: Path to text file

        Returns:
            Text content

        Raises:
            DocumentLoadError: If loading fails
        """
        try:
            path = Path(source)

            if not path.exists():
                raise DocumentLoadError(f"File not found: {source}")

            with open(path, encoding=self.encoding) as f:
                text = f.read()

            if not text.strip():
                raise DocumentLoadError(f"Empty file: {source}")

            return text

        except UnicodeDecodeError as e:
            raise DocumentLoadError(
                f"Failed to decode text file with encoding '{self.encoding}': {source}"
            ) from e
        except Exception as e:
            if isinstance(e, DocumentLoadError):
                raise
            raise DocumentLoadError(f"Failed to load text file: {str(e)}") from e

    def get_metadata(self, source: str) -> dict[str, Any]:
        """
        Get text file metadata.

        Args:
            source: Path to text file

        Returns:
            Dictionary with file metadata
        """
        path = Path(source)

        metadata: dict[str, Any] = {
            "file_path": str(path.absolute()),
            "file_name": path.name,
            "file_type": "txt",
            "encoding": self.encoding,
        }

        if path.exists():
            metadata["file_size_bytes"] = path.stat().st_size

        return metadata
