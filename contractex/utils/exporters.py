"""Export utilities for various formats."""

import json
from pathlib import Path
from typing import Union

from contractex.core.models import Contract


class JSONExporter:
    """Export contracts to JSON format."""

    @staticmethod
    def export(contract: Contract, file_path: Union[str, Path]) -> None:
        """
        Export contract to JSON file.

        Args:
            contract: Contract to export
            file_path: Path to save JSON file
        """
        json_str = contract.model_dump_json(indent=2)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(json_str)

    @staticmethod
    def export_batch(contracts: list[Contract], file_path: Union[str, Path]) -> None:
        """
        Export multiple contracts to JSON file.

        Args:
            contracts: List of contracts to export
            file_path: Path to save JSON file
        """
        data = [contract.model_dump() for contract in contracts]

        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str)


class CSVExporter:
    """Export contracts to CSV format."""

    @staticmethod
    def export_clauses(contract: Contract, file_path: Union[str, Path]) -> None:
        """
        Export contract clauses to CSV file.

        Args:
            contract: Contract to export
            file_path: Path to save CSV file
        """
        try:
            import pandas as pd  # noqa: F401
        except ImportError as e:
            raise ImportError(
                "pandas required for CSV export. Install with: pip install pandas"
            ) from e

        df = contract.to_dataframe()
        df.to_csv(file_path, index=False, encoding="utf-8")

    @staticmethod
    def export_financial_terms(contract: Contract, file_path: Union[str, Path]) -> None:
        """
        Export financial terms to CSV file.

        Args:
            contract: Contract to export
            file_path: Path to save CSV file
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas required for CSV export. Install with: pip install pandas"
            ) from e

        if not contract.financial_terms:
            return

        data = [
            {
                "term_type": ft.term_type,
                "amount": str(ft.amount) if ft.amount else "",
                "currency": ft.currency,
                "frequency": ft.frequency or "",
                "due_date": str(ft.due_date) if ft.due_date else "",
                "description": ft.description,
                "confidence": ft.confidence,
            }
            for ft in contract.financial_terms
        ]

        df = pd.DataFrame(data)
        df.to_csv(file_path, index=False, encoding="utf-8")


class ExcelExporter:
    """Export contracts to Excel format."""

    @staticmethod
    def export(contract: Contract, file_path: Union[str, Path]) -> None:
        """
        Export contract to Excel file with multiple sheets.

        Args:
            contract: Contract to export
            file_path: Path to save Excel file
        """
        contract.to_excel(str(file_path))

    @staticmethod
    def export_batch(contracts: list[Contract], file_path: Union[str, Path]) -> None:
        """
        Export multiple contracts to Excel file.

        Args:
            contracts: List of contracts to export
            file_path: Path to save Excel file
        """
        try:
            import pandas as pd
        except ImportError as e:
            raise ImportError(
                "pandas and openpyxl required. Install with: pip install pandas openpyxl"
            ) from e

        with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
            # Summary sheet
            summary_data = []
            for i, contract in enumerate(contracts, 1):
                summary_data.append(
                    {
                        "Contract #": i,
                        "Type": str(contract.contract_type),
                        "Parties": ", ".join([p.name for p in contract.parties]),
                        "Effective Date": (
                            str(contract.effective_date) if contract.effective_date else ""
                        ),
                        "Expiration Date": (
                            str(contract.expiration_date) if contract.expiration_date else ""
                        ),
                        "Clause Count": len(contract.clauses),
                        "Risk Count": len(contract.risks),
                    }
                )

            pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)

            # Individual contract sheets (limit to first 10 to avoid too many sheets)
            for i, contract in enumerate(contracts[:10], 1):
                if contract.clauses:
                    df = contract.to_dataframe()
                    sheet_name = f"Contract {i}"[:31]  # Excel sheet name limit
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
