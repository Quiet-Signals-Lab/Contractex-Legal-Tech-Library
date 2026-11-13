"""contractex.analysis.compare: what changed between two extraction results."""

from __future__ import annotations

from contractex.analysis import compare
from contractex.core.models import Clause, Contract

CAP = (
    "Supplier's aggregate liability shall not exceed the fees paid in the preceding twelve months."
)
UNLIMITED = "Supplier's liability under this Agreement is unlimited."


def clause(text: str, clause_type: str = "cap_on_liability", section: str = "") -> dict:
    return {"clause_type": clause_type, "text": text, "section_number": section}


class TestCompare:
    def test_identical_versions_have_no_changes(self):
        diff = compare([clause(CAP)], [clause(CAP)])
        assert (diff.added_clauses, diff.removed_clauses, diff.modified_clauses) == ([], [], [])

    def test_added_and_removed_types(self):
        diff = compare([clause(CAP)], [clause("Delaware law governs.", "governing_law")])
        assert diff.added_clauses == ["governing_law"]
        assert diff.removed_clauses == ["cap_on_liability"]

    def test_minor_edit_is_one_modified_clause(self):
        edited = CAP.replace("twelve", "six")
        (change,) = compare([clause(CAP)], [clause(edited)]).modified_clauses
        assert (change.text_v1, change.text_v2) == (CAP, edited)
        assert 0.85 <= change.similarity < 1.0

    def test_rewritten_clause_is_reported(self):
        changes = compare([clause(CAP)], [clause(UNLIMITED)]).modified_clauses
        assert [(c.text_v1, c.text_v2) for c in changes] == [(CAP, ""), ("", UNLIMITED)]
        assert all(c.clause_type == "cap_on_liability" for c in changes)

    def test_clause_added_to_an_existing_type_is_reported(self):
        extra = "Nothing in this Agreement limits liability for fraud."
        (change,) = compare([clause(CAP)], [clause(CAP), clause(extra)]).modified_clauses
        assert (change.text_v1, change.text_v2) == ("", extra)

    def test_clause_removed_from_an_existing_type_is_reported(self):
        extra = "Nothing in this Agreement limits liability for fraud."
        (change,) = compare([clause(CAP), clause(extra)], [clause(CAP)]).modified_clauses
        assert (change.text_v1, change.text_v2) == (extra, "")

    def test_summary_names_added_and_removed_clauses(self):
        summary = compare([clause(CAP)], [clause(UNLIMITED)]).summary()
        assert "cap_on_liability (removed)" in summary
        assert "cap_on_liability (added)" in summary

    def test_accepts_contract_objects_and_reports_section_refs(self):
        v1 = Contract(clauses=[Clause(clause_type="term", text="Two years.", section_number="3")])
        v2 = Contract(clauses=[Clause(clause_type="term", text="Two years!", section_number="4")])
        (change,) = compare(v1, v2, similarity_threshold=0.5).modified_clauses
        assert (change.section_ref_v1, change.section_ref_v2) == ("3", "4")

    def test_order_is_deterministic(self):
        v1 = [clause("a b c d", t) for t in ("zeta", "alpha", "mid")]
        v2 = [clause("a b c e", t) for t in ("mid", "zeta", "alpha")]
        changes = compare(v1, v2, similarity_threshold=0.5).modified_clauses
        assert [c.clause_type for c in changes] == ["alpha", "mid", "zeta"]
