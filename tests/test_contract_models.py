"""Contract model string forms and ``Contract.compare_with``."""

from __future__ import annotations

from decimal import Decimal

from contractex.core.models import Clause, Contract, FinancialTerm, Party


def test_str_prints_enum_values_not_member_names():
    # f"{member}" of a (str, Enum) prints "PartyRole.PROVIDER" from Python 3.12
    party = Party(name="Acme Corp", role="provider")
    contract = Contract(contract_type="nda", parties=[party])
    assert str(party) == "Acme Corp (provider)"
    assert str(contract) == "Contract(nda, parties=[Acme Corp])"
    assert repr(contract) == "Contract(type=nda, parties=1, clauses=0, risks=0)"
    assert str(Contract()) == "Contract(None, parties=[])"


def contract(liability: str, fee: str) -> Contract:
    return Contract(
        contract_type="nda",
        parties=[Party(name="Acme Inc")],
        clauses=[
            Clause(clause_type="limitation_of_liability", text=liability),
            Clause(clause_type="governing_law", text="Delaware law governs."),
        ],
        financial_terms=[
            FinancialTerm(term_type="payment_amount", amount=Decimal(fee), description="fee")
        ],
    )


CAPPED = "Supplier's liability is capped at $1,000,000."
UNLIMITED = "Supplier's liability is unlimited and includes consequential damages."


class TestCompareWith:
    def test_identical_contracts_are_fully_similar(self):
        result = contract(CAPPED, "50000").compare_with(contract(CAPPED, "50000.00"))
        assert result.overall_similarity == 1.0
        assert result.clause_similarity == 1.0
        assert result.clause_differences == []
        assert result.financial_differences == []

    def test_different_clause_text_is_a_difference(self):
        result = contract(CAPPED, "50000").compare_with(contract(UNLIMITED, "50000"))
        assert len(result.clause_differences) == 1
        assert "limitation_of_liability" in result.clause_differences[0]
        assert result.clause_similarity < 1.0
        assert result.overall_similarity < 1.0

    def test_different_amount_is_a_difference(self):
        result = contract(CAPPED, "50000").compare_with(contract(CAPPED, "5000000"))
        assert len(result.financial_differences) == 1
        assert "payment_amount" in result.financial_differences[0]
        assert "50000" in result.financial_differences[0]
        assert result.overall_similarity < 1.0
