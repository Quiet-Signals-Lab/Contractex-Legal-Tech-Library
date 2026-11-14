"""DOCX reading order, AutoLoader options and OCR failures."""

from __future__ import annotations

import sys
import types

import docx
import pytest

from contractex.exceptions import DocumentLoadError
from contractex.loaders import AutoLoader, DOCXLoader, PDFLoader
from tests.test_pdf_loader import make_pdf


@pytest.fixture
def fee_schedule_docx(tmp_path):
    """Paragraph, table with a merged title row, paragraph; two sections sharing a header."""
    document = docx.Document()
    document.sections[0].header.paragraphs[0].text = "CONFIDENTIAL"
    document.sections[0].footer.paragraphs[0].text = "Page footer"
    document.add_paragraph("1. Fees. The fees are set out in the table below.")
    table = document.add_table(rows=3, cols=3)
    table.cell(0, 0).merge(table.cell(0, 2)).text = "Schedule of Fees"
    for column, value in enumerate(["Year 1", "USD 10,000", "net 30"]):
        table.cell(1, column).text = value
    table.cell(1, 0).merge(table.cell(2, 0))  # "Year 1" spans two rows
    table.cell(2, 1).text = "USD 12,000"
    table.cell(2, 2).text = "net 60"
    document.add_paragraph("2. Term. This Agreement lasts two years.")
    document.add_section()
    document.add_paragraph("3. Notices.")
    path = tmp_path / "fees.docx"
    document.save(str(path))
    return str(path)


class TestDOCXLoader:
    def test_body_is_in_reading_order_without_repeats(self, fee_schedule_docx):
        assert DOCXLoader().load(fee_schedule_docx).splitlines() == [
            "CONFIDENTIAL",
            "1. Fees. The fees are set out in the table below.",
            "Schedule of Fees",
            "Year 1 | USD 10,000 | net 30",
            "USD 12,000 | net 60",
            "2. Term. This Agreement lasts two years.",
            "3. Notices.",
            "Page footer",
        ]

    def test_headers_and_footers_can_be_left_out(self, fee_schedule_docx):
        text = DOCXLoader(include_headers=False, include_footers=False).load(fee_schedule_docx)
        assert "CONFIDENTIAL" not in text
        assert "Page footer" not in text
        assert text.startswith("1. Fees.")


class TestAutoLoader:
    def test_each_loader_gets_only_its_own_options(self):
        loader = AutoLoader(ocr_enabled=True, include_headers=False, encoding="latin-1")
        assert loader.loaders[".pdf"].ocr_enabled is True
        assert loader.loaders[".docx"].include_headers is False
        assert loader.loaders[".txt"].encoding == "latin-1"

    def test_unknown_option_is_an_error(self):
        with pytest.raises(TypeError, match="ocr_enabeld"):
            AutoLoader(ocr_enabeld=True)

    def test_no_options(self, tmp_path):
        path = tmp_path / "a.txt"
        path.write_text("Plain text contract.")
        assert AutoLoader().load(str(path)) == "Plain text contract."


def test_ocr_failure_raises_instead_of_returning_empty_text(tmp_path, monkeypatch):
    pytest.importorskip("PIL")

    def image_to_string(image):
        raise OSError("tesseract is not installed or it's not in your PATH")

    monkeypatch.setitem(
        sys.modules, "pytesseract", types.SimpleNamespace(image_to_string=image_to_string)
    )
    path = tmp_path / "scan.pdf"
    path.write_bytes(make_pdf([""]))
    with pytest.raises(DocumentLoadError, match="OCR failed.*tesseract is not installed"):
        PDFLoader(ocr_enabled=True).load(str(path))
