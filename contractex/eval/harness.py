"""
EvalHarness — runs eval suites against an extractor callable and reports metrics.

The harness is deliberately extractor-agnostic.  Callers supply an
``extractor_fn`` with the signature::

    def extractor_fn(case: EvalCase) -> dict[str, Any]:
        ...

This accepts an ``EvalCase`` and returns a ``dict`` mapping field names to
extracted values.  The harness handles timing, error capture, metric
accumulation, and report generation.

Typical integration::

    from contractex.eval import EvalHarness, EvalSuite

    # Wire up your pipeline
    def my_extractor(case: EvalCase) -> dict:
        doc = pipeline.process(case.input_path or case.input_text)
        return doc.extracted_fields

    harness = EvalHarness(extractor_fn=my_extractor)
    suite   = EvalSuite.load("tests/eval/immigration_cases.yaml")
    metrics = harness.run(suite)

    print(metrics.report())
    metrics.assert_min_field_accuracy(0.90)   # CI gate
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

from contractex.eval.cases import EvalCase, EvalSuite
from contractex.eval.metrics import (
    CaseResult,
    ExtractionMetrics,
    FieldResult,
    PrivacyCaseResult,
    PrivacyMetrics,
    _values_match,
)
from contractex.privacy.router import PrivacyBlockedError

logger = logging.getLogger(__name__)

_FAILED = object()  # sentinel: the callable for this stage raised


def _attempt(fn: Callable[[EvalCase], Any], case: EvalCase, errors: list[str]) -> Any:
    """Call one privacy-eval stage; on an exception record it and return _FAILED."""
    try:
        return fn(case)
    except Exception as exc:
        errors.append(f"{type(exc).__name__}: {exc}")
        logger.warning("Privacy eval case %r raised %r", case.id, exc)
        return _FAILED


def _blocked_by(router_fn: Callable[[EvalCase], bool], case: EvalCase) -> bool:
    try:
        return bool(router_fn(case))
    except PrivacyBlockedError:
        return True


# Type alias: any callable (EvalCase) → dict[str, Any]
ExtractorFn = Callable[[EvalCase], dict[str, Any]]


class EvalHarness:
    """
    Run eval suites and compute extraction quality metrics.

    Args:
        extractor_fn: Callable that accepts an ``EvalCase`` and returns a
                      ``dict`` of extracted values.  May raise; errors are
                      caught and counted as ``error_cases`` unless
                      ``fail_fast=True``.
        fail_fast:    Stop at the first extractor error instead of continuing.

    Example::

        harness = EvalHarness(my_extractor, fail_fast=False)
        metrics = harness.run(suite)
        assert metrics.field_accuracy >= 0.90
    """

    def __init__(
        self,
        extractor_fn: ExtractorFn,
        fail_fast: bool = False,
    ) -> None:
        self.extractor_fn = extractor_fn
        self.fail_fast = fail_fast

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, suite: EvalSuite) -> ExtractionMetrics:
        """
        Run all cases in *suite* and return aggregated metrics.

        Args:
            suite: The ``EvalSuite`` to evaluate.

        Returns:
            ``ExtractionMetrics`` with per-field and aggregate stats plus the
            full list of ``CaseResult`` objects for inspection.
        """
        logger.info(
            "EvalHarness starting: suite=%r, cases=%d",
            suite.name,
            len(suite),
        )
        metrics = ExtractionMetrics(total_cases=len(suite.cases))

        for case in suite.cases:
            result = self._run_case(case)
            metrics.case_results.append(result)
            self._accumulate(metrics, result)

            if self.fail_fast and result.error is not None:
                logger.error(
                    "fail_fast=True: stopping after error in case %r: %s",
                    case.id,
                    result.error,
                )
                break

        logger.info(
            "EvalHarness complete: field_accuracy=%.1f%%, case_accuracy=%.1f%%",
            metrics.field_accuracy * 100,
            metrics.case_accuracy * 100,
        )
        return metrics

    def run_case(self, case: EvalCase) -> CaseResult:
        """Run a single eval case (useful for debugging a specific failure)."""
        return self._run_case(case)

    # ------------------------------------------------------------------
    # Privacy evaluation
    # ------------------------------------------------------------------

    def run_privacy(
        self,
        suite: EvalSuite,
        *,
        pii_detector_fn: Callable[[EvalCase], list[str]] | None = None,
        redactor_fn: Callable[[EvalCase], int] | None = None,
        router_fn: Callable[[EvalCase], bool] | None = None,
    ) -> PrivacyMetrics:
        """
        Run privacy / redaction evaluation across *suite*.

        Args:
            suite:           The ``EvalSuite`` to evaluate.
            pii_detector_fn: Callable ``(EvalCase) → list[str]`` — returns the
                             entity types detected (e.g. ``["PERSON", "EMAIL_ADDRESS"]``).
                             Required for cases with ``expected_pii_entities``.
            redactor_fn:     Callable ``(EvalCase) → int`` — returns the number
                             of redaction spans applied.  Required for cases with
                             ``expected_redaction_count``.
            router_fn:       Callable ``(EvalCase) → bool`` — returns ``True``
                             when the privacy router blocks the LLM call.  Raising
                             ``PrivacyBlockedError`` also counts as blocked.  Blocking
                             is scored only when a router_fn is given.

        Any other exception raised by one of these callables is recorded in the
        case's ``error`` and scored as a failure for that metric.

        Returns:
            ``PrivacyMetrics`` with precision/recall/F1 for PII detection and
            blocking accuracy.
        """
        logger.info(
            "EvalHarness.run_privacy starting: suite=%r, cases=%d",
            suite.name,
            len(suite),
        )
        case_results: list[PrivacyCaseResult] = []

        for case in suite.cases:
            start = time.monotonic()
            errors: list[str] = []

            detected_pii = actual_redaction_count = was_blocked = None
            if case.expected_pii_entities is not None and pii_detector_fn is not None:
                detected_pii = _attempt(pii_detector_fn, case, errors)
            if case.expected_redaction_count is not None and redactor_fn is not None:
                actual_redaction_count = _attempt(redactor_fn, case, errors)
            if router_fn is not None:
                was_blocked = _attempt(lambda c: _blocked_by(router_fn, c), case, errors)

            result = PrivacyCaseResult.compute(
                case_id=case.id,
                expected_pii=case.expected_pii_entities,
                detected_pii=[] if detected_pii is _FAILED else detected_pii,
                expected_redaction_count=case.expected_redaction_count,
                actual_redaction_count=(
                    None if actual_redaction_count is _FAILED else actual_redaction_count
                ),
                should_be_blocked=case.should_be_blocked,
                was_blocked=None if was_blocked is _FAILED else was_blocked,
                error="; ".join(errors) or None,
                elapsed=round(time.monotonic() - start, 3),
            )
            # A stage that crashed counts as a failure, never as a pass or a skip
            if detected_pii is _FAILED:
                result.pii_precision = result.pii_recall = result.pii_f1 = 0.0
            if actual_redaction_count is _FAILED:
                result.redaction_count_match = False
            if was_blocked is _FAILED:
                result.blocking_correct = False
            case_results.append(result)

        metrics = PrivacyMetrics.from_case_results(case_results)
        logger.info(
            "EvalHarness.run_privacy complete: pii_f1=%s, blocking_acc=%s",
            f"{metrics.pii_f1:.1%}" if metrics.pii_f1 is not None else "n/a",
            f"{metrics.blocking_accuracy:.1%}" if metrics.blocking_accuracy is not None else "n/a",
        )
        return metrics

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_case(self, case: EvalCase) -> CaseResult:
        """Execute one case and return its CaseResult."""
        logger.debug("Running eval case %r", case.id)
        start = time.monotonic()

        try:
            actual_fields = self.extractor_fn(case)
        except Exception as exc:
            elapsed = time.monotonic() - start
            logger.warning(
                "Eval case %r raised %s: %s (%.2fs)",
                case.id,
                type(exc).__name__,
                exc,
                elapsed,
            )
            return CaseResult(
                case_id=case.id,
                error=f"{type(exc).__name__}: {exc}",
                elapsed_seconds=round(elapsed, 3),
            )

        elapsed = time.monotonic() - start
        logger.debug("Case %r completed in %.2fs", case.id, elapsed)

        field_results: list[FieldResult] = []
        for field_name, expected_value in case.expected_fields.items():
            actual_value = actual_fields.get(field_name)
            match = _values_match(expected_value, actual_value)
            field_results.append(
                FieldResult(
                    field_name=field_name,
                    expected=expected_value,
                    actual=actual_value,
                    match=match,
                    weight=case.get_weight(field_name),
                )
            )

        return CaseResult(
            case_id=case.id,
            field_results=field_results,
            elapsed_seconds=round(elapsed, 3),
        )

    @staticmethod
    def _accumulate(metrics: ExtractionMetrics, result: CaseResult) -> None:
        """Merge one CaseResult into the aggregate ExtractionMetrics."""
        if result.error is not None:
            metrics.error_cases += 1
            return

        if result.passed:
            metrics.passed_cases += 1

        metrics.total_weighted_score += result.weighted_score
        metrics.total_max_score += result.max_score

        for fr in result.field_results:
            if fr.field_name not in metrics.field_stats:
                metrics.field_stats[fr.field_name] = {"correct": 0, "total": 0}
            stats = metrics.field_stats[fr.field_name]
            stats["total"] += 1
            if fr.match:
                stats["correct"] += 1
