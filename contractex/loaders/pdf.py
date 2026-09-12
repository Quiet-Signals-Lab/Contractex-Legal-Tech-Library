"""PDF document loader using pypdfium2 (PDFium; BSD-3-Clause / Apache-2.0)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contractex.exceptions import DocumentLoadError
from contractex.loaders.base import DocumentLoader


class PDFLoader(DocumentLoader):
    """
    PDF document loader using pypdfium2, the Python binding for Google's PDFium.

    Extracts the text layer of each page; pages are joined with a blank line.
    Scanned pages have no text layer: with ``ocr_enabled=True`` those pages
    are rendered at 300 dpi and passed to Tesseract (``contractex[ocr]``).
    """

    def __init__(
        self,
        ocr_enabled: bool = False,
        preserve_layout: bool = False,
        extract_images: bool = False,
    ):
        """
        Initialize PDF loader.

        Args:
            ocr_enabled: OCR pages that have no text layer (needs contractex[ocr])
            preserve_layout: Order text runs top-to-bottom, left-to-right by
                position instead of content-stream order
            extract_images: Extract images from PDF (not implemented)
        """
        self.ocr_enabled = ocr_enabled
        self.preserve_layout = preserve_layout
        self.extract_images = extract_images

        try:
            import pypdfium2

            self.pdfium = pypdfium2
        except ImportError as e:
            raise DocumentLoadError(
                "pypdfium2 not installed. Install with: pip install pypdfium2"
            ) from e

    def load(self, source: str) -> str:
        """
        Load PDF and extract text.

        Args:
            source: Path to PDF file

        Returns:
            Extracted text content

        Raises:
            DocumentLoadError: If loading fails
        """
        try:
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"PDF file not found: {source}")
            return pdf_text(self.pdfium.PdfDocument(source), self._page_text)
        except Exception as e:
            raise DocumentLoadError(f"Failed to load PDF: {str(e)}") from e

    def _page_text(self, page: Any) -> str:
        text = page_text(page, self.preserve_layout)
        if self.ocr_enabled and not text.strip():
            text = self._ocr_page(page)
        return text

    def _ocr_page(self, page: Any) -> str:
        """
        Perform OCR on a PDF page using Tesseract.

        Args:
            page: pypdfium2 page object

        Returns:
            OCR'd text
        """
        try:
            import pytesseract

            image = page.render(scale=300 / 72).to_pil()
            text: str = pytesseract.image_to_string(image)
            return text

        except ImportError as e:
            raise DocumentLoadError(
                "OCR dependencies not installed. Install with: pip install 'contractex[ocr]'"
            ) from e
        except Exception:
            # Silently fail and return empty string
            return ""

    def get_metadata(self, source: str) -> dict[str, Any]:
        """Get PDF metadata."""
        metadata = super().get_metadata(source)

        try:
            pdf = self.pdfium.PdfDocument(source)
            try:
                metadata.update({"page_count": len(pdf), "pdf_metadata": pdf.get_metadata_dict()})
            finally:
                pdf.close()
        except Exception:
            pass

        return metadata

    def supports(self, file_path: str) -> bool:
        """Check if file is a PDF."""
        return Path(file_path).suffix.lower() == ".pdf"


def page_text(page: Any, preserve_layout: bool = False) -> str:
    """Text layer of one pypdfium2 page, with ``\n`` line endings."""
    textpage = page.get_textpage()
    try:
        if preserve_layout:
            # Text runs by position: top to bottom (PDF y grows upwards), then left to right
            rects = [textpage.get_rect(i) for i in range(textpage.count_rects())]
            rects.sort(key=lambda r: (-r[3], r[0]))
            text = "\n".join(textpage.get_text_bounded(*r) for r in rects)
        else:
            text = textpage.get_text_range()
    finally:
        textpage.close()
    return str(text).replace("\r\n", "\n").replace("\r", "\n")


def pdf_text(pdf: Any, extract: Any = page_text) -> str:
    """Join the text of every page of an open pypdfium2 document, then close it."""
    try:
        return "\n\n".join(extract(pdf[i]) for i in range(len(pdf)))
    finally:
        pdf.close()
