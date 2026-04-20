"""
Unit tests for EvalHarness, EvalCase, EvalSuite, and ExtractionMetrics.

No LLM, no network, no database — all extractor_fns are pure Python stubs.
"""

import json
from pathlib import Path

import pytest

from contractex.eval import EvalCase, EvalHarness, EvalSuite, ExtractionMetrics
from contractex.eval.metrics import CaseResult, FieldResult, _values_match


# ---------------------------------------------------------------------------
# _values_match helper
# ---------------------------------------------------------------------------


class TestValuesMatch:
    def test_exact_string_match(self):
        assert _values_match("SMITH", "SMITH") is True

    def test_case_insensitive_string(self):
        assert _values_match("Smith", "SMITH") is True

    def test_whitespace_stripped(self):
        assert _values_match("GARCIA", "  GARCIA  ") is True

    def test_string_mismatch(self):
        assert _values_match("SMITH", "JONES") is False

    def test_none_actual_fails(self):
        assert _values_match("SMITH", None) is False

    def test_bool_strict(self):
        assert _values_match(True, True) is True
        assert _values_match(True, False) is False
        # bool should not match 1 (bool is subclass of int, but we guard for it)
        assert _values_match(True, 1) is False

    def test_int_equality(self):
        assert _values_match(42, 42) is True
        assert _values_match(42, 43) is False

    def test_float_equality(self):
        assert _values_match(3.14, 3.14) is True


# ---------------------------------------------------------------------------
# EvalCase
# ---------------------------------------------------------------------------


class TestEvalCase:
    def test_minimal_case(self):
        case = EvalCase(id="case-1")
        assert case.description == ""
        assert case.expected_fields == {}
        assert case.field_weights == {}

    def test_get_weight_default(self):
        case = EvalCase(id="case-1", expected_fields={"name": "SMITH"})
        assert case.get_weight("name") == 1.0

    def test_get_weight_override(self):
        case = EvalCase(
            id="case-1",
            expected_fields={"citation": "17 U.S.C. § 107"},
            field_weights={"citation": 2.0},
        )
        assert case.get_weight("citation") == 2.0

    def test_has_input_path(self):
        case = EvalCase(id="case-1", input_path="tests/fixtures/doc.pdf")
        assert case.has_input() is True

    def test_has_input_text(self):
        case = EvalCase(id="case-1", input_text="some inline text")
        assert case.has_input() is True

    def test_has_input_neither(self):
        case = EvalCase(id="case-1")
        assert case.has_input() is False


# ---------------------------------------------------------------------------
# EvalSuite
# ---------------------------------------------------------------------------


class TestEvalSuite:
    def _make_suite(self) -> EvalSuite:
        cases = [
            EvalCase(id="c1", tags=["statute"], expected_fields={"jurisdiction": "US-Federal"}),
            EvalCase(id="c2", tags=["passport"], expected_fields={"surname": "SMITH"}),
            EvalCase(id="c3", tags=["passport"], doc_type="identity_doc"),
        ]
        return EvalSuite(name="test", cases=cases)

    def test_len(self):
        suite = self._make_suite()
        assert len(suite) == 3

    def test_filter_by_tag(self):
        suite = self._make_suite()
        filtered = suite.filter_by_tag("passport")
        assert len(filtered) == 2
        assert all("passport" in c.tags for c in filtered.cases)

    def test_filter_by_doc_type(self):
        suite = self._make_suite()
        filtered = suite.filter_by_doc_type("identity_doc")
        assert len(filtered) == 1

    def test_from_cases(self):
        cases = [EvalCase(id="x1"), EvalCase(id="x2")]
        suite = EvalSuite.from_cases(cases, name="my-suite")
        assert suite.name == "my-suite"
        assert len(suite) == 2

    def test_from_json(self, tmp_path):
        data = [
            {"id": "j1", "expected_fields": {"name": "GARCIA"}},
            {"id": "j2", "expected_fields": {"dob": "1990-01-15"}},
        ]
        path = tmp_path / "suite.json"
        path.write_text(json.dumps(data))
        suite = EvalSuite.from_json(path)
        assert len(suite) == 2
        assert suite.cases[0].id == "j1"

    def test_from_json_with_name_key(self, tmp_path):
        data = {
            "name": "named-suite",
            "description": "A test suite",
            "cases": [{"id": "c1"}],
        }
        path = tmp_path / "named.json"
        path.write_text(json.dumps(data))
        suite = EvalSuite.from_json(path)
        assert suite.name == "named-suite"

    def test_load_json(self, tmp_path):
        data = [{"id": "c1"}]
        path = tmp_path / "s.json"
        path.write_text(json.dumps(data))
        suite = EvalSuite.load(path)
        assert len(suite) == 1

    def test_load_yaml(self, tmp_path):
        pytest.importorskip("yaml", reason="pyyaml not installed")
        content = "- id: y1\n  expected_fields:\n    name: SMITH\n"
        path = tmp_path / "suite.yaml"
        path.write_text(content)
        suite = EvalSuite.load(path)
        assert len(suite) == 1
        assert suite.cases[0].expected_fields["name"] == "SMITH"

    def test_load_unsupported_extension(self, tmp_path):
        path = tmp_path / "suite.csv"
        path.write_text("id,expected_fields\n")
        with pytest.raises(ValueError, match="Unsupported"):
            EvalSuite.load(path)

    def test_repr(self):
        suite = self._make_suite()
        assert "EvalSuite" in repr(suite)
        assert "test" in repr(suite)


# ---------------------------------------------------------------------------
# FieldResult and CaseResult
# ---------------------------------------------------------------------------


class TestFieldResult:
    def test_match_weighted_score(self):
        fr = FieldResult(field_name="name", expected="A", actual="A", match=True, weight=2.0)
        assert fr.weighted_score == 2.0

    def test_no_match_weighted_score(self):
        fr = FieldResult(field_name="name", expected="A", actual="B", match=False, weight=2.0)
        assert fr.weighted_score == 0.0

    def test_str_pass(self):
        fr = FieldResult(field_name="name", expected="A", actual="A", match=True)
        assert "PASS" in str(fr)

    def test_str_fail(self):
        fr = FieldResult(field_name="name", expected="A", actual="B", match=False)
        assert "FAIL" in str(fr)


class TestCaseResult:
    def _make_result(self, matches: list[bool]) -> CaseResult:
        frs = [
            FieldResult(field_name=f"f{i}", expected="x", actual="x" if m else "y", match=m)
            for i, m in enumerate(matches)
        ]
        return CaseResult(case_id="test", field_results=frs)

    def test_passed_all_match(self):
        result = self._make_result([True, True, True])
        assert result.passed is True

    def test_passed_false_on_mismatch(self):
        result = self._make_result([True, False, True])
        assert result.passed is False

    def test_passed_false_on_error(self):
        result = CaseResult(case_id="e", error="something went wrong")
        assert result.passed is False

    def test_score_ratio_all_pass(self):
        result = self._make_result([True, True])
        assert result.score_ratio == 1.0

    def test_score_ratio_partial(self):
        result = self._make_result([True, False])
        assert result.score_ratio == pytest.approx(0.5)

    def test_failed_fields(self):
        result = self._make_result([True, False, True])
        assert len(result.failed_fields) == 1


# ---------------------------------------------------------------------------
# EvalHarness — core
# ---------------------------------------------------------------------------


def _perfect_extractor(case: EvalCase) -> dict:
    """Returns the exact expected fields — simulates 100% accuracy."""
    return dict(case.expected_fields)


def _empty_extractor(case: EvalCase) -> dict:
    """Returns nothing — simulates total failure."""
    return {}


def _error_extractor(case: EvalCase) -> dict:
    """Always raises — simulates extractor crash."""
    raise RuntimeError("OCR engine unavailable")


class TestEvalHarness:
    def _suite(self) -> EvalSuite:
        return EvalSuite.from_cases([
            EvalCase(id="c1", expected_fields={"jurisdiction": "US-Federal", "citation": "17 U.S.C. § 107"}),
            EvalCase(id="c2", expected_fields={"surname": "GARCIA", "given_name": "JOSE"}),
        ])

    def test_perfect_extractor_field_accuracy(self):
        harness = EvalHarness(_perfect_extractor)
        metrics = harness.run(self._suite())
        assert metrics.field_accuracy == 1.0
        assert metrics.case_accuracy == 1.0

    def test_empty_extractor_field_accuracy(self):
        harness = EvalHarness(_empty_extractor)
        metrics = harness.run(self._suite())
        assert metrics.field_accuracy == 0.0
        assert metrics.passed_cases == 0

    def test_error_extractor_counts_errors(self):
        harness = EvalHarness(_error_extractor)
        metrics = harness.run(self._suite())
        assert metrics.error_cases == 2
        assert metrics.passed_cases == 0

    def test_fail_fast_stops_on_first_error(self):
        harness = EvalHarness(_error_extractor, fail_fast=True)
        metrics = harness.run(self._suite())
        # Should stop after the first error
        assert metrics.error_cases == 1

    def test_mixed_extractor(self):
        suite = EvalSuite.from_cases([
            EvalCase(id="ok", expected_fields={"name": "SMITH"}),
            EvalCase(id="bad", expected_fields={"name": "JONES"}),
        ])

        def mixed(case: EvalCase) -> dict:
            if case.id == "ok":
                return {"name": "SMITH"}
            return {"name": "WRONG"}

        harness = EvalHarness(mixed)
        metrics = harness.run(suite)
        assert metrics.passed_cases == 1
        assert metrics.field_accuracy == pytest.approx(0.5)

    def test_case_results_populated(self):
        harness = EvalHarness(_perfect_extractor)
        metrics = harness.run(self._suite())
        assert len(metrics.case_results) == 2

    def test_field_stats_populated(self):
        harness = EvalHarness(_perfect_extractor)
        metrics = harness.run(self._suite())
        assert "jurisdiction" in metrics.field_stats
        assert metrics.field_stats["jurisdiction"]["correct"] == 1

    def test_run_case_single(self):
        harness = EvalHarness(_perfect_extractor)
        case = EvalCase(id="solo", expected_fields={"x": "val"})
        result = harness.run_case(case)
        assert result.passed is True

    def test_weighted_field_accuracy(self):
        suite = EvalSuite.from_cases([
            EvalCase(
                id="weighted",
                expected_fields={"citation": "§ 107", "title": "Fair Use"},
                field_weights={"citation": 3.0, "title": 1.0},
            )
        ])

        def partial(case: EvalCase) -> dict:
            return {"citation": "§ 107"}  # title missing → weight 1 lost

        harness = EvalHarness(partial)
        metrics = harness.run(suite)
        # 3 / (3 + 1) = 0.75
        assert metrics.field_accuracy == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# ExtractionMetrics — report and assertion helpers
# ---------------------------------------------------------------------------


class TestExtractionMetrics:
    def _make_metrics(self, field_acc: float, case_acc: float) -> ExtractionMetrics:
        m = ExtractionMetrics(total_cases=10)
        m.passed_cases = int(case_acc * 10)
        m.total_weighted_score = field_acc * 10
        m.total_max_score = 10.0
        return m

    def test_field_accuracy_property(self):
        m = self._make_metrics(0.85, 0.70)
        assert m.field_accuracy == pytest.approx(0.85)

    def test_case_accuracy_property(self):
        m = self._make_metrics(0.85, 0.70)
        assert m.case_accuracy == pytest.approx(0.70)

    def test_report_contains_key_metrics(self):
        m = self._make_metrics(0.90, 0.80)
        report = m.report()
        assert "90%" in report or "90.0%" in report
        assert "80%" in report or "80.0%" in report

    def test_assert_min_field_accuracy_passes(self):
        m = self._make_metrics(0.95, 0.80)
        m.assert_min_field_accuracy(0.90)  # Should not raise

    def test_assert_min_field_accuracy_fails(self):
        m = self._make_metrics(0.75, 0.60)
        with pytest.raises(AssertionError, match="75"):
            m.assert_min_field_accuracy(0.90)

    def test_assert_min_case_accuracy_passes(self):
        m = self._make_metrics(0.90, 0.85)
        m.assert_min_case_accuracy(0.80)  # Should not raise

    def test_assert_min_case_accuracy_fails(self):
        m = self._make_metrics(0.90, 0.50)
        with pytest.raises(AssertionError, match="50"):
            m.assert_min_case_accuracy(0.80)

    def test_no_cases_field_accuracy_zero(self):
        m = ExtractionMetrics()
        assert m.field_accuracy == 0.0

    def test_no_cases_case_accuracy_zero(self):
        m = ExtractionMetrics()
        assert m.case_accuracy == 0.0
