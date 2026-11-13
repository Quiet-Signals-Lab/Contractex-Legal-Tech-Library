"""DOCX document loader using python-docx."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contractex.exceptions import DocumentLoadError
from contractex.loaders.base import DocumentLoader


class DOCXLoader(DocumentLoader):
    """
    DOCX document loader using python-docx.

    Supports Microsoft Word .docx files.  Paragraphs and tables come out in
    reading order; table rows are joined with " | " and a merged cell appears
    once.
    """

    def __init__(self, include_headers: bool = True, include_footers: bool = True):
        """
        Initialize DOCX loader.

        Args:
            include_headers: Include header text
            include_footers: Include footer text
        """
        self.include_headers = include_headers
        self.include_footers = include_footers

        # Check python-docx availability
        try:
            import docx

            self.docx = docx
        except ImportError as e:
            raise DocumentLoadError(
                "python-docx not installed. Install with: pip install python-docx"
            ) from e

    def load(self, source: str) -> str:
        """
        Load DOCX and extract text.

        Args:
            source: Path to DOCX file

        Returns:
            Extracted text content

        Raises:
            DocumentLoadError: If loading fails
        """
        try:
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"DOCX file not found: {source}")

            # Load document
            doc = self.docx.Document(source)  # type: ignore[attr-defined]

            text_parts = []

            # Extract headers (a section linked to the previous one repeats its header)
            if self.include_headers:
                for section in doc.sections:
                    header = section.header
                    if header.is_linked_to_previous:
                        continue
                    for paragraph in header.paragraphs:
                        if paragraph.text.strip():
                            text_parts.append(paragraph.text)

            # Extract main content: paragraphs and tables in document order
            for block in doc.iter_inner_content():
                if hasattr(block, "rows"):
                    seen = set()  # python-docx returns a merged cell once per cell it spans
                    for row in block.rows:
                        cells = []
                        for cell in row.cells:
                            if cell._tc not in seen:
                                seen.add(cell._tc)
                                cells.append(cell.text.strip())
                        row_text = " | ".join(cells)
                        if row_text.strip():
                            text_parts.append(row_text)
                elif block.text.strip():
                    text_parts.append(block.text)

            # Extract footers
            if self.include_footers:
                for section in doc.sections:
                    footer = section.footer
                    if footer.is_linked_to_previous:
                        continue
                    for paragraph in footer.paragraphs:
                        if paragraph.text.strip():
                            text_parts.append(paragraph.text)

            # Combine all parts
            full_text = "\n".join(text_parts)

            return full_text

        except Exception as e:
            raise DocumentLoadError(f"Failed to load DOCX: {str(e)}") from e

    def get_metadata(self, source: str) -> dict[str, Any]:
        """Get DOCX metadata."""
        metadata = super().get_metadata(source)

        try:
            doc = self.docx.Document(source)  # type: ignore[attr-defined]

            # Add DOCX-specific metadata
            core_properties = doc.core_properties

            metadata.update(
                {
                    "author": core_properties.author,
                    "created": core_properties.created,
                    "modified": core_properties.modified,
                    "title": core_properties.title,
                    "subject": core_properties.subject,
                    "paragraph_count": len(doc.paragraphs),
                    "table_count": len(doc.tables),
                }
            )

        except Exception:
            pass

        return metadata

    def supports(self, file_path: str) -> bool:
        """Check if file is a DOCX."""
        return Path(file_path).suffix.lower() == ".docx"
