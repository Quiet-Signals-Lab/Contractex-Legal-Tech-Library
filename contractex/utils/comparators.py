"""Comparator utilities for comparing contracts."""

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
        common_types = types1 & types2
        for clause_type in common_types:
            clauses1 = [c for c in c1.clauses if c.clause_type == clause_type]
            clauses2 = [c for c in c2.clauses if c.clause_type == clause_type]

            if len(clauses1) != len(clauses2):
                diffs.append(
                    f"Different number of '{clause_type}' clauses: "
                    f"{len(clauses1)} vs {len(clauses2)}"
                )

        return diffs

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

        types1 = {c.clause_type for c in c1.clauses}
        types2 = {c.clause_type for c in c2.clauses}

        intersection = len(types1 & types2)
        union = len(types1 | types2)

        return intersection / union if union > 0 else 0.0

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

        # Normalize: fewer differences = higher similarity
        # Assume max 20 differences for normalization
        similarity = max(0.0, 1.0 - (total_diffs / 20.0))

        # Blend with clause similarity
        if comparison.clause_similarity > 0:
            similarity = (similarity + comparison.clause_similarity) / 2

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
