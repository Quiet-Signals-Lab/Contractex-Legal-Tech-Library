"""Comparator utilities for comparing contracts."""

from __future__ import annotations

from difflib import SequenceMatcher

from contractex.core.models import Contract, ContractComparison


class ContractComparator:
    """Utility for comparing two contracts."""

    def compare(self, contract1: Contract, contract2: Contract) -> ContractComparison:
        """
        Compare two contracts and identify differences.

        Args:
            contract1: First contract
            contract2: Second contract

        Returns:
            ContractComparison with identified differences
        """
        comparison = ContractComparison(
            contract1=contract1,
            contract2=contract2,
            overall_similarity=0.0,
            clause_similarity=0.0,
        )

        # Compare parties
        comparison.party_differences = self._compare_parties(contract1, contract2)

        # Compare clauses
        comparison.clause_differences = self._compare_clauses(contract1, contract2)

        # Compare financial terms
        comparison.financial_differences = self._compare_financial(contract1, contract2)

        # Compare dates
        comparison.date_differences = self._compare_dates(contract1, contract2)

        # Calculate similarity scores
        comparison.clause_similarity = self._calculate_clause_similarity(contract1, contract2)
        comparison.overall_similarity = self._calculate_overall_similarity(comparison)

        return comparison

    def _compare_parties(self, c1: Contract, c2: Contract) -> list[str]:
        """Compare parties between contracts."""
        diffs = []

        parties1 = {p.name for p in c1.parties}
        parties2 = {p.name for p in c2.parties}

        # Parties only in contract1
        only_in_1 = parties1 - parties2
        if only_in_1:
            diffs.append(f"Parties only in Contract 1: {', '.join(only_in_1)}")

        # Parties only in contract2
        only_in_2 = parties2 - parties1
        if only_in_2:
            diffs.append(f"Parties only in Contract 2: {', '.join(only_in_2)}")

        # Role differences
        common_parties = parties1 & parties2
        for party_name in common_parties:
            p1 = next((p for p in c1.parties if p.name == party_name), None)
            p2 = next((p for p in c2.parties if p.name == party_name), None)

            if p1 and p2 and p1.role != p2.role:
                diffs.append(f"'{party_name}' has different roles: {p1.role} vs {p2.role}")

        return diffs

    def _compare_clauses(self, c1: Contract, c2: Contract) -> list[str]:
        """Compare clauses between contracts."""
        diffs = []

        # Get clause types
        types1 = {c.clause_type for c in c1.clauses}
        types2 = {c.clause_type for c in c2.clauses}

        only_in_1 = types1 - types2
        if only_in_1:
            diffs.append(f"Clause types only in Contract 1: {', '.join(only_in_1)}")

        only_in_2 = types2 - types1
        if only_in_2:
            diffs.append(f"Clause types only in Contract 2: {', '.join(only_in_2)}")

        # Compare common clause types
        texts1, texts2 = self._text_by_type(c1), self._text_by_type(c2)
        for clause_type in sorted(types1 & types2):
            clauses1 = [c for c in c1.clauses if c.clause_type == clause_type]
            clauses2 = [c for c in c2.clauses if c.clause_type == clause_type]

            if len(clauses1) != len(clauses2):
                diffs.append(
                    f"Different number of '{clause_type}' clauses: "
                    f"{len(clauses1)} vs {len(clauses2)}"
                )
            elif texts1[clause_type] != texts2[clause_type]:
                ratio = compare_clause_texts(texts1[clause_type], texts2[clause_type])
                diffs.append(f"'{clause_type}' clause text differs ({ratio:.0%} similar)")

        return diffs

    @staticmethod
    def _text_by_type(contract: Contract) -> dict[str, str]:
        """Clause text per clause type; clauses of one type are joined in document order."""
        texts: dict[str, list[str]] = {}
        for clause in contract.clauses:
            texts.setdefault(clause.clause_type, []).append(clause.text)
        return {clause_type: "\n".join(parts) for clause_type, parts in texts.items()}

    def _compare_financial(self, c1: Contract, c2: Contract) -> list[str]:
        """Compare financial terms."""
        diffs = []

        if len(c1.financial_terms) != len(c2.financial_terms):
            diffs.append(
                f"Different number of financial terms: "
                f"{len(c1.financial_terms)} vs {len(c2.financial_terms)}"
            )

        # Compare by term type
        types1 = {ft.term_type for ft in c1.financial_terms}
        types2 = {ft.term_type for ft in c2.financial_terms}

        if types1 != types2:
            only_in_1 = types1 - types2
            only_in_2 = types2 - types1

            if only_in_1:
                diffs.append(f"Financial terms only in Contract 1: {', '.join(only_in_1)}")
            if only_in_2:
                diffs.append(f"Financial terms only in Contract 2: {', '.join(only_in_2)}")

        # Same term type, different amount or currency
        for term_type in sorted(types1 & types2):
            amounts1, amounts2 = (
                sorted(
                    (
                        (ft.currency, ft.amount)
                        for ft in c.financial_terms
                        if ft.term_type == term_type
                    ),
                    key=lambda a: (a[0], a[1] is not None, a[1] or 0),
                )
                for c in (c1, c2)
            )
            if amounts1 != amounts2:  # Decimal("50000") == Decimal("50000.00")
                shown1, shown2 = (
                    ", ".join(f"{currency} {amount}" for currency, amount in amounts)
                    for amounts in (amounts1, amounts2)
                )
                diffs.append(f"'{term_type}' differs: {shown1} vs {shown2}")

        return diffs

    def _compare_dates(self, c1: Contract, c2: Contract) -> list[str]:
        """Compare important dates."""
        diffs = []

        if c1.effective_date != c2.effective_date:
            diffs.append(f"Different effective dates: {c1.effective_date} vs {c2.effective_date}")

        if c1.expiration_date != c2.expiration_date:
            diffs.append(
                f"Different expiration dates: {c1.expiration_date} vs {c2.expiration_date}"
            )

        return diffs

    def _calculate_clause_similarity(self, c1: Contract, c2: Contract) -> float:
        """Calculate similarity score for clauses."""
        if not c1.clauses or not c2.clauses:
            return 0.0

        # Jaccard over clause types, each shared type weighted by how alike its text is
        texts1, texts2 = self._text_by_type(c1), self._text_by_type(c2)
        shared = sum(
            compare_clause_texts(texts1[t], texts2[t]) for t in texts1.keys() & texts2.keys()
        )

        return shared / len(texts1.keys() | texts2.keys())

    def _calculate_overall_similarity(self, comparison: ContractComparison) -> float:
        """Calculate overall similarity score."""
        # Simple average of component similarities
        # Could be weighted based on importance

        total_diffs = (
            len(comparison.party_differences)
            + len(comparison.clause_differences)
            + len(comparison.financial_differences)
            + len(comparison.date_differences)
        )

        # Convert difference count to a 0-1 score using a smooth decay so that
        # any number of diffs is handled without an arbitrary cap.
        diff_score = 1.0 / (1 + total_diffs)

        # Blend with clause structural similarity (Jaccard over clause types)
        if comparison.clause_similarity > 0:
            similarity = (diff_score + comparison.clause_similarity) / 2
        else:
            similarity = diff_score

        return round(similarity, 3)


def compare_clause_texts(text1: str, text2: str) -> float:
    """
    Compare two clause texts and return similarity score.

    Args:
        text1: First clause text
        text2: Second clause text

    Returns:
        Similarity score between 0.0 and 1.0
    """
    return SequenceMatcher(None, text1, text2).ratio()
