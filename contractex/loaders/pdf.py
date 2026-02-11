"""PDF document loader using PyMuPDF."""

from pathlib import Path
from typing import Any

from contractex.exceptions import DocumentLoadError
from contractex.loaders.base import DocumentLoader


class PDFLoader(DocumentLoader):
    """
    PDF document loader using PyMuPDF (fitz).

    Supports text extraction with optional OCR fallback for scanned documents.
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
            ocr_enabled: Enable OCR for scanned PDFs
            preserve_layout: Try to preserve document layout
            extract_images: Extract images from PDF
        """
        self.ocr_enabled = ocr_enabled
        self.preserve_layout = preserve_layout
        self.extract_images = extract_images

        # Check PyMuPDF availability
        try:
            import fitz
            self.fitz = fitz
        except ImportError as e:
            raise DocumentLoadError(
                "PyMuPDF not installed. Install with: pip install pymupdf"
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

            # Open PDF
            doc = self.fitz.open(source)

            # Extract text from all pages
            text_parts = []

            for page_num in range(len(doc)):
                page = doc[page_num]

                # Extract text
                if self.preserve_layout:
                    text = page.get_text("blocks")
                    # Sort blocks by position and join
                    blocks = sorted(text, key=lambda b: (b[1], b[0]))
                    page_text = "\n".join(b[4] for b in blocks if len(b) > 4)
                else:
                    page_text = page.get_text()

                # If text is empty and OCR is enabled, try OCR
                if self.ocr_enabled and not page_text.strip():
                    page_text = self._ocr_page(page)

                text_parts.append(page_text)

            doc.close()

            # Combine all pages
            full_text = "\n\n".join(text_parts)

            return full_text

        except Exception as e:
            raise DocumentLoadError(f"Failed to load PDF: {str(e)}") from e

    def _ocr_page(self, page) -> str:
        """
        Perform OCR on a PDF page using Tesseract.

        Args:
            page: PyMuPDF page object

        Returns:
            OCR'd text
        """
        try:
            import io

            import pytesseract
            from PIL import Image

            # Render page to image
            pix = page.get_pixmap(dpi=300)
            img_data = pix.tobytes("png")
            img = Image.open(io.BytesIO(img_data))

            # Perform OCR
            text = pytesseract.image_to_string(img)

            return text

        except ImportError as e:
            raise DocumentLoadError(
                "OCR dependencies not installed. "
                "Install with: pip install pytesseract pillow"
            ) from e
        except Exception:
            # Silently fail and return empty string
            return ""

    def get_metadata(self, source: str) -> dict[str, Any]:
        """Get PDF metadata."""
        metadata = super().get_metadata(source)

        try:
            doc = self.fitz.open(source)

            # Add PDF-specific metadata
            metadata.update({
                'page_count': len(doc),
                'pdf_metadata': doc.metadata,
                'is_encrypted': doc.is_encrypted,
            })

            doc.close()

        except Exception:
            pass

        return metadata

    def supports(self, file_path: str) -> bool:
        """Check if file is a PDF."""
        return Path(file_path).suffix.lower() == '.pdf'
