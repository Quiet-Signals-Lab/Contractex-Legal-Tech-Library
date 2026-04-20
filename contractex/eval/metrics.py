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
    return expected == actual


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
            f"[{status}] {self.field_name}: "
            f"expected={self.expected!r}, actual={self.actual!r}"
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
        return (
            self.total_weighted_score / self.total_max_score
            if self.total_max_score
            else 0.0
        )

    def report(self) -> str:
        """Return a human-readable summary table."""
        sep = "=" * 62
        lines = [
            sep,
            "  ContractEx Eval Report",
            sep,
            f"  Suite size:     {self.total_cases} cases",
            f"  Passed:         {self.passed_cases} "
            f"({self.case_accuracy:.1%} case accuracy)",
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
                lines.append(
                    f"  {fname:<32s} {correct:>8d} {n:>7d}  {acc:.0%}"
                )

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
