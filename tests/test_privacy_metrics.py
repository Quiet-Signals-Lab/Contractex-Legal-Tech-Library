"""
PrivacyMetrics and EvalHarness.run_privacy: the CI gates must fail when the
pipeline under test leaks or crashes, and must never pass vacuously.
"""

from __future__ import annotations

import pytest

from contractex.eval import EvalCase, EvalHarness, EvalSuite
from contractex.eval.metrics import PrivacyCaseResult, PrivacyMetrics
from contractex.privacy import PrivacyAwareLLMRouter, PrivacyProfile
from contractex.privacy.router import PrivacyBlockedError
from tests._providers import SpyProvider


def defect(reason: str):
    return pytest.mark.xfail(strict=True, reason=f"known defect: {reason}")


HARNESS = EvalHarness(extractor_fn=lambda case: {})


def suite(*cases: EvalCase) -> EvalSuite:
    return EvalSuite.from_cases(list(cases))


class TestPIIRecall:
    def test_recall_and_precision(self):
        m = HARNESS.run_privacy(
            suite(EvalCase(id="a", input_text="x", expected_pii_entities=["PERSON", "EMAIL"])),
            pii_detector_fn=lambda c: ["PERSON", "PHONE"],
        )
        assert m.pii_recall == 0.5 and m.pii_precision == 0.5

    def test_gate_fails_below_threshold(self):
        m = HARNESS.run_privacy(
            suite(EvalCase(id="a", input_text="x", expected_pii_entities=["PERSON"])),
            pii_detector_fn=lambda c: [],
        )
        with pytest.raises(AssertionError):
            m.assert_min_pii_recall(0.95)

    def test_gate_refuses_to_pass_without_data(self):
        with pytest.raises(AssertionError):
            HARNESS.run_privacy(suite(EvalCase(id="a", input_text="x"))).assert_min_pii_recall(0.5)

    @defect("a detector that raises is excluded from recall instead of counting as a miss")
    def test_crashing_detector_counts_as_a_miss(self):
        cases = [
            EvalCase(id="ok", input_text="x", expected_pii_entities=["PERSON"]),
            EvalCase(id="bad", input_text="y", expected_pii_entities=["PERSON"]),
        ]

        def detector(case):
            if case.id == "bad":
                raise RuntimeError("detector crashed")
            return ["PERSON"]

        m = HARNESS.run_privacy(suite(*cases), pii_detector_fn=detector)
        with pytest.raises(AssertionError):
            m.assert_min_pii_recall(0.95)


def _router_fn(case: EvalCase) -> bool:
    """Route a one-line prompt through the real router; return True if blocked."""

    class Doc:
        privacy_profile = PrivacyProfile(sensitivity=case.metadata["sensitivity"])

    PrivacyAwareLLMRouter().route_completion(Doc(), case.input_text or "", SpyProvider())
    return False


def blocking_case(case_id: str, sensitivity: str, should_block: bool) -> EvalCase:
    return EvalCase(
        id=case_id,
        input_text="hello",
        should_be_blocked=should_block,
        metadata={"sensitivity": sensitivity},
    )


class TestBlocking:
    def test_gate_fails_when_a_block_is_missed(self):
        m = HARNESS.run_privacy(
            suite(blocking_case("s", "secret", True)), router_fn=lambda case: False
        )
        with pytest.raises(AssertionError):
            m.assert_perfect_blocking()

    @defect("blocking_accuracy is computed with no router_fn, so the gate passes vacuously")
    def test_gate_refuses_to_pass_without_a_router(self):
        m = HARNESS.run_privacy(suite(blocking_case("p", "public", False)))
        with pytest.raises(AssertionError):
            m.assert_perfect_blocking()

    @defect("a router that raises PrivacyBlockedError is recorded as an error, not a block")
    def test_real_router_raising_counts_as_blocked(self):
        m = HARNESS.run_privacy(
            suite(blocking_case("s", "secret", True), blocking_case("p", "public", False)),
            router_fn=_router_fn,
        )
        m.assert_perfect_blocking()

    @defect("a router that crashes is scored correct on should-not-block cases")
    def test_crashing_router_is_not_scored_correct(self):
        def router_fn(case):
            raise RuntimeError("provider down")

        m = HARNESS.run_privacy(suite(blocking_case("p", "public", False)), router_fn=router_fn)
        with pytest.raises(AssertionError):
            m.assert_perfect_blocking()


class TestAggregation:
    def test_from_case_results_counts(self):
        results = [
            PrivacyCaseResult.compute(
                case_id="a",
                expected_pii=["PERSON"],
                detected_pii=["PERSON"],
                expected_redaction_count=2,
                actual_redaction_count=2,
                should_be_blocked=True,
                was_blocked=True,
            )
        ]
        m = PrivacyMetrics.from_case_results(results)
        assert (m.pii_recall, m.blocking_accuracy, m.redaction_accuracy) == (1.0, 1.0, 1.0)
        assert "Blocking accuracy" in m.report()

    def test_blocked_error_type_is_importable_for_router_fns(self):
        assert issubclass(PrivacyBlockedError, Exception)
