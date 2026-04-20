"""
Extraction quality metrics for the eval harness.

Metrics hierarchy
-----------------
FieldResult  — pass/fail + weight for one field in one case
CaseResult   — aggregates FieldResults for one eval case
ExtractionMetrics — aggregates CaseResults across a full EvalSuite

Weighted field accuracy
-----------------------
The core metric is *weighted field accuracy*: the sum of weights of matching
fields divided by the sum of all field weights.  This lets the eval suite
author declare that ``citation`` accuracy matters twice as much as
``governing_law`` without changing the case structure.

  field_accuracy = Σ(weight_i * match_i) / Σ(weight_i)

Comparison semantics
--------------------
``_values_match`` performs type-aware, lenient comparison:
  - Strings:  case-insensitive strip comparison
  - Booleans: strict equality (True ≠ "true")
  - Numbers:  exact equality
  - None / missing actual: always False
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Comparison helper
# ---------------------------------------------------------------------------


def _values_match(expected: Any, actual: Any) -> bool:
    """
    Flexible equality comparison for eval cases.

    * ``str`` values: strip + lower-case comparison (handles whitespace variance)
    * ``bool`` values: strict equality (avoids ``True == 1`` confusion)
    * Everything else: ``==``
    * If *actual* is ``None`` (field was not extracted): always ``False``
    """
    if actual is None:
        return False
    # Check bool before int/float since bool is a subclass of int
    if isinstance(expected, bool):
        return isinstance(actual, bool) and expected == actual
    if isinstance(expected, str) and isinstance(actual, str):
        return expected.strip().lower() == actual.strip().lower()
    return bool(expected == actual)


# ---------------------------------------------------------------------------
# Per-field result
# ---------------------------------------------------------------------------


class FieldResult(BaseModel):
    """Evaluation result for a single field within one eval case."""

    field_name: str
    expected: Any
    actual: Any
    match: bool
    weight: float = Field(1.0, gt=0.0)

    @property
    def weighted_score(self) -> float:
        """Weight if matched, else 0."""
        return self.weight if self.match else 0.0

    def __str__(self) -> str:
        status = "PASS" if self.match else "FAIL"
        return (
            f"[{status}] {self.field_name}: " f"expected={self.expected!r}, actual={self.actual!r}"
        )


# ---------------------------------------------------------------------------
# Per-case result
# ---------------------------------------------------------------------------


class CaseResult(BaseModel):
    """Evaluation result for a single eval case."""

    case_id: str
    field_results: list[FieldResult] = Field(default_factory=list)
    error: str | None = Field(
        None,
        description="Error message if the extractor raised an exception",
    )
    elapsed_seconds: float | None = None

    @property
    def weighted_score(self) -> float:
        return sum(r.weighted_score for r in self.field_results)

    @property
    def max_score(self) -> float:
        return sum(r.weight for r in self.field_results)

    @property
    def score_ratio(self) -> float:
        """Weighted fraction of fields that matched (0.0–1.0)."""
        return self.weighted_score / self.max_score if self.max_score else 0.0

    @property
    def passed(self) -> bool:
        """True iff no error AND every field matched."""
        return self.error is None and all(r.match for r in self.field_results)

    @property
    def failed_fields(self) -> list[FieldResult]:
        return [r for r in self.field_results if not r.match]


# ---------------------------------------------------------------------------
# Aggregate metrics
# ---------------------------------------------------------------------------


class ExtractionMetrics(BaseModel):
    """Aggregate quality metrics across an entire EvalSuite run."""

    total_cases: int = 0
    passed_cases: int = 0
    error_cases: int = 0

    total_weighted_score: float = 0.0
    total_max_score: float = 0.0

    # Per-field stats: {field_name: {"correct": int, "total": int}}
    field_stats: dict[str, dict[str, Any]] = Field(default_factory=dict)

    # Detailed per-case results (populated by EvalHarness)
    case_results: list[CaseResult] = Field(default_factory=list)

    @property
    def case_accuracy(self) -> float:
        """Fraction of cases where *all* fields matched (no partial credit)."""
        return self.passed_cases / self.total_cases if self.total_cases else 0.0

    @property
    def field_accuracy(self) -> float:
        """Weighted fraction of individual fields that matched."""
        return self.total_weighted_score / self.total_max_score if self.total_max_score else 0.0

    def report(self) -> str:
        """Return a human-readable summary table."""
        sep = "=" * 62
        lines = [
            sep,
            "  ContractEx Eval Report",
            sep,
            f"  Suite size:     {self.total_cases} cases",
            f"  Passed:         {self.passed_cases} " f"({self.case_accuracy:.1%} case accuracy)",
            f"  Errors:         {self.error_cases}",
            f"  Field accuracy: {self.field_accuracy:.1%} (weighted)",
        ]

        if self.field_stats:
            lines.append("")
            lines.append("  Per-field accuracy:")
            lines.append(f"  {'Field':<32s} {'Correct':>8s} {'Total':>7s}  Acc")
            lines.append("  " + "-" * 56)
            for fname, stats in sorted(self.field_stats.items()):
                n = stats["total"]
                correct = stats["correct"]
                acc = correct / n if n else 0.0
                lines.append(f"  {fname:<32s} {correct:>8d} {n:>7d}  {acc:.0%}")

        lines.append(sep)
        return "\n".join(lines)

    def assert_min_field_accuracy(self, threshold: float) -> None:
        """
        Assert that weighted field accuracy is at or above *threshold*.

        Designed for use in pytest::

            metrics.assert_min_field_accuracy(0.90)

        Raises:
            AssertionError: With a descriptive message including the report.
        """
        if self.field_accuracy < threshold:
            raise AssertionError(
                f"Field accuracy {self.field_accuracy:.1%} < required {threshold:.1%}\n"
                + self.report()
            )

    def assert_min_case_accuracy(self, threshold: float) -> None:
        """Assert that case accuracy is at or above *threshold*."""
        if self.case_accuracy < threshold:
            raise AssertionError(
                f"Case accuracy {self.case_accuracy:.1%} < required {threshold:.1%}\n"
                + self.report()
            )


# ---------------------------------------------------------------------------
# Privacy-specific result and metrics
# ---------------------------------------------------------------------------


class PrivacyCaseResult(BaseModel):
    """Privacy / redaction evaluation result for a single eval case."""

    case_id: str

    # PII detection quality
    expected_pii_entities: list[str] = Field(default_factory=list)
    detected_pii_entities: list[str] = Field(default_factory=list)
    pii_precision: float | None = None
    pii_recall: float | None = None
    pii_f1: float | None = None

    # Redaction span count check
    expected_redaction_count: int | None = None
    actual_redaction_count: int | None = None
    redaction_count_match: bool | None = None

    # Blocking behaviour
    should_be_blocked: bool = False
    was_blocked: bool = False
    blocking_correct: bool | None = None

    error: str | None = None
    elapsed_seconds: float | None = None

    @classmethod
    def compute(
        cls,
        case_id: str,
        expected_pii: list[str] | None,
        detected_pii: list[str] | None,
        expected_redaction_count: int | None,
        actual_redaction_count: int | None,
        should_be_blocked: bool,
        was_blocked: bool,
        error: str | None = None,
        elapsed: float | None = None,
    ) -> "PrivacyCaseResult":
        """Compute PII precision/recall/F1 and blocking accuracy."""
        result = cls(
            case_id=case_id,
            expected_pii_entities=expected_pii or [],
            detected_pii_entities=detected_pii or [],
            expected_redaction_count=expected_redaction_count,
            actual_redaction_count=actual_redaction_count,
            should_be_blocked=should_be_blocked,
            was_blocked=was_blocked,
            error=error,
            elapsed_seconds=elapsed,
        )

        # PII detection precision / recall
        if expected_pii is not None and detected_pii is not None:
            exp_set = set(e.upper() for e in expected_pii)
            det_set = set(e.upper() for e in detected_pii)
            tp = len(exp_set & det_set)
            result.pii_precision = tp / len(det_set) if det_set else 0.0
            result.pii_recall = tp / len(exp_set) if exp_set else 1.0
            denom = result.pii_precision + result.pii_recall
            result.pii_f1 = (
                2 * result.pii_precision * result.pii_recall / denom if denom else 0.0
            )

        # Redaction count
        if expected_redaction_count is not None and actual_redaction_count is not None:
            result.redaction_count_match = actual_redaction_count >= expected_redaction_count

        # Blocking accuracy
        result.blocking_correct = was_blocked == should_be_blocked

        return result


class PrivacyMetrics(BaseModel):
    """Aggregate privacy / redaction metrics across an EvalSuite run."""

    total_cases: int = 0
    pii_cases: int = 0           # cases with expected_pii_entities set
    blocking_cases: int = 0      # cases with should_be_blocked set

    # Micro-averaged PII precision / recall / F1 (across all pii_cases)
    pii_precision: float | None = None
    pii_recall: float | None = None
    pii_f1: float | None = None

    # Fraction of blocking decisions that were correct
    blocking_accuracy: float | None = None

    # Fraction of redaction-count cases where actual >= expected
    redaction_accuracy: float | None = None

    case_results: list[PrivacyCaseResult] = Field(default_factory=list)

    @classmethod
    def from_case_results(cls, results: list[PrivacyCaseResult]) -> "PrivacyMetrics":
        """Aggregate a list of PrivacyCaseResult into summary metrics."""
        m = cls(total_cases=len(results))

        pii_prec_sum = pii_rec_sum = 0.0
        pii_n = blocking_correct = blocking_n = redaction_correct = redaction_n = 0

        for r in results:
            if r.pii_precision is not None:
                pii_prec_sum += r.pii_precision
                pii_rec_sum += r.pii_recall or 0.0
                pii_n += 1
            if r.blocking_correct is not None:
                blocking_n += 1
                if r.blocking_correct:
                    blocking_correct += 1
            if r.redaction_count_match is not None:
                redaction_n += 1
                if r.redaction_count_match:
                    redaction_correct += 1

        m.pii_cases = pii_n
        m.blocking_cases = blocking_n

        if pii_n:
            prec = pii_prec_sum / pii_n
            rec = pii_rec_sum / pii_n
            m.pii_precision = prec
            m.pii_recall = rec
            m.pii_f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0

        if blocking_n:
            m.blocking_accuracy = blocking_correct / blocking_n

        if redaction_n:
            m.redaction_accuracy = redaction_correct / redaction_n

        m.case_results = results
        return m

    def report(self) -> str:
        """Return a human-readable privacy metrics summary."""
        sep = "=" * 62
        lines = [
            sep,
            "  ContractEx Privacy Eval Report",
            sep,
            f"  Total cases:        {self.total_cases}",
            f"  PII detection cases:{self.pii_cases}",
            f"  Blocking cases:     {self.blocking_cases}",
        ]
        if self.pii_precision is not None:
            lines += [
                f"  PII precision:      {self.pii_precision:.1%}",
                f"  PII recall:         {self.pii_recall:.1%}",
                f"  PII F1:             {self.pii_f1:.1%}",
            ]
        if self.blocking_accuracy is not None:
            lines.append(f"  Blocking accuracy:  {self.blocking_accuracy:.1%}")
        if self.redaction_accuracy is not None:
            lines.append(f"  Redaction accuracy: {self.redaction_accuracy:.1%}")
        lines.append(sep)
        return "\n".join(lines)

    def assert_min_pii_recall(self, threshold: float) -> None:
        """Assert that PII recall is at or above *threshold*."""
        if self.pii_recall is None:
            raise AssertionError("No PII recall data available — no cases with expected_pii_entities")
        if self.pii_recall < threshold:
            raise AssertionError(
                f"PII recall {self.pii_recall:.1%} < required {threshold:.1%}\n" + self.report()
            )

    def assert_perfect_blocking(self) -> None:
        """Assert that all blocking decisions were correct."""
        if self.blocking_accuracy is None:
            raise AssertionError("No blocking data available — no cases with should_be_blocked")
        if self.blocking_accuracy < 1.0:
            raise AssertionError(
                f"Blocking accuracy {self.blocking_accuracy:.1%} != 100%\n" + self.report()
            )
