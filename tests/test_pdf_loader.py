"""
PDF loading (file and URL paths).  PDFs are generated in-memory so the suite
needs no binary fixtures: each page holds lines of Helvetica text.
"""

from __future__ import annotations

import sys
import types

import pytest

from contractex.exceptions import DocumentLoadError
from contractex.loaders import PDFLoader
from contractex.loaders.source_adapter import URLLoader


def make_pdf(pages: list[str]) -> bytes:
    """A minimal valid PDF; each page's lines are drawn top to bottom."""

    def esc(s: str) -> str:
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")

    n = len(pages)
    kids = " ".join(f"{4 + 2 * i} 0 R" for i in range(n))
    objs = [
        "<< /Type /Catalog /Pages 2 0 R >>",
        f"<< /Type /Pages /Kids [{kids}] /Count {n} >>",
        "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    for i, text in enumerate(pages):
        shown = " ".join(f"({esc(line)}) Tj T*" for line in text.split("\n") if line)
        ops = f"BT /F1 12 Tf 72 720 Td 14 TL {shown} ET"
        objs.append(
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {5 + 2 * i} 0 R >>"
        )
        objs.append(f"<< /Length {len(ops)} >>\nstream\n{ops}\nendstream")

    out = b"%PDF-1.4\n"
    offsets = []
    for i, obj in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    out += b"".join(f"{off:010d} 00000 n \n".encode() for off in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


@pytest.fixture
def two_page_pdf(tmp_path):
    path = tmp_path / "contract.pdf"
    path.write_bytes(make_pdf(["1. Term.\nThis Agreement lasts one year.", "2. Law.\nDelaware."]))
    return path


def lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


class TestPDFLoader:
    def test_extracts_all_pages_in_order(self, two_page_pdf):
        text = PDFLoader().load(str(two_page_pdf))
        assert lines(text) == [
            "1. Term.",
            "This Agreement lasts one year.",
            "2. Law.",
            "Delaware.",
        ]

    def test_pages_separated_by_blank_line(self, two_page_pdf):
        text = PDFLoader().load(str(two_page_pdf)).replace("\r\n", "\n")
        assert "\n\n" in text.strip()

    def test_preserve_layout_keeps_top_to_bottom_order(self, two_page_pdf):
        text = PDFLoader(preserve_layout=True).load(str(two_page_pdf))
        assert lines(text) == [
            "1. Term.",
            "This Agreement lasts one year.",
            "2. Law.",
            "Delaware.",
        ]

    def test_missing_file(self, tmp_path):
        with pytest.raises(DocumentLoadError):
            PDFLoader().load(str(tmp_path / "missing.pdf"))

    def test_not_a_pdf(self, tmp_path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"this is not a pdf")
        with pytest.raises(DocumentLoadError):
            PDFLoader().load(str(bad))

    def test_page_count_metadata(self, two_page_pdf):
        assert PDFLoader().get_metadata(str(two_page_pdf))["page_count"] == 2

    def test_ocr_fallback_for_blank_page(self, tmp_path, monkeypatch):
        pytest.importorskip("PIL")
        seen = []

        def image_to_string(image):
            seen.append(image.size)
            return "OCR TEXT"

        monkeypatch.setitem(
            sys.modules, "pytesseract", types.SimpleNamespace(image_to_string=image_to_string)
        )
        path = tmp_path / "scan.pdf"
        path.write_bytes(make_pdf([""]))
        assert PDFLoader(ocr_enabled=True).load(str(path)).strip() == "OCR TEXT"
        assert seen and seen[0][0] > 612  # rendered above 72 dpi

    def test_url_loader_pdf_bytes(self):
        text = URLLoader._load_pdf_bytes(make_pdf(["Hello from a URL."]), "https://docs.test/a.pdf")
        assert lines(text) == ["Hello from a URL."]
