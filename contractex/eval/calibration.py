"""
Confidence calibration tools for extraction quality analysis.

A well-calibrated model should have accuracy ≈ confidence.
If your extractor reports 0.9 confidence on average but is correct only
70% of the time, the confidence scores are over-confident and need
recalibration.

Usage::

    from contractex.eval.calibration import CalibrationAnalyzer

    # Build a calibration set from extraction results with known ground truth
    analyzer = CalibrationAnalyzer()
    for clause, is_correct in your_labeled_pairs:
        analyzer.add(confidence=clause.confidence, correct=is_correct)

    print(analyzer.summary())
    analyzer.plot(save_path="calibration.png")   # optional matplotlib
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_N_BINS = 10


@dataclass
class CalibrationBin:
    """One confidence decile bin."""

    lower: float
    upper: float
    count: int = 0
    correct: int = 0

    @property
    def mean_confidence(self) -> float:
        return (self.lower + self.upper) / 2

    @property
    def accuracy(self) -> float:
        return self.correct / self.count if self.count > 0 else 0.0

    @property
    def expected_error(self) -> float:
        """Expected calibration error contribution (weighted)."""
        return abs(self.accuracy - self.mean_confidence) * self.count


@dataclass
class CalibrationResult:
    """Result of a calibration analysis."""

    bins: list[CalibrationBin]
    total_samples: int

    def ece(self) -> float:
        """Expected Calibration Error (ECE) — lower is better."""
        if self.total_samples == 0:
            return 0.0
        return sum(b.expected_error for b in self.bins) / self.total_samples

    def summary(self) -> str:
        lines = [
            f"\nCalibration Analysis  (n={self.total_samples})",
            f"Expected Calibration Error (ECE): {self.ece():.4f}",
            "",
            f"{'Confidence Range':<22} {'Count':>7} {'Accuracy':>10} {'Expected':>10}",
            "─" * 54,
        ]
        for b in self.bins:
            if b.count == 0:
                continue
            lines.append(
                f"{b.lower:.1f}–{b.upper:.1f}{'':>14} {b.count:>7} "
                f"{b.accuracy:>10.2f} {b.mean_confidence:>10.2f}"
            )
        return "\n".join(lines)


class CalibrationAnalyzer:
    """
    Accumulate (confidence, correct) pairs and compute calibration metrics.
    """

    def __init__(self, n_bins: int = _N_BINS) -> None:
        self._n_bins = n_bins
        self._pairs: list[tuple[float, bool]] = []

    def add(self, confidence: float, correct: bool) -> None:
        """Add a single (confidence, correctness) observation."""
        self._pairs.append((confidence, correct))

    def add_batch(self, pairs: list[tuple[float, bool]]) -> None:
        """Add multiple (confidence, correctness) pairs."""
        self._pairs.extend(pairs)

    def analyze(self) -> CalibrationResult:
        """Compute calibration bins and ECE."""
        step = 1.0 / self._n_bins
        bins = [CalibrationBin(lower=i * step, upper=(i + 1) * step) for i in range(self._n_bins)]

        for conf, correct in self._pairs:
            bin_idx = min(int(conf * self._n_bins), self._n_bins - 1)
            bins[bin_idx].count += 1
            if correct:
                bins[bin_idx].correct += 1

        return CalibrationResult(bins=bins, total_samples=len(self._pairs))

    def plot(self, save_path: str | None = None, title: str = "Confidence Calibration") -> None:
        """
        Plot reliability diagram.

        Args:
            save_path: If provided, save to this path instead of showing.
            title: Plot title.

        Raises:
            ImportError: If matplotlib is not installed.
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError as err:
            raise ImportError("matplotlib is required. pip install matplotlib") from err

        result = self.analyze()
        non_empty = [b for b in result.bins if b.count > 0]

        confs = [b.mean_confidence for b in non_empty]
        accs = [b.accuracy for b in non_empty]

        fig, ax = plt.subplots(figsize=(6, 5))
        ax.plot([0, 1], [0, 1], "k--", label="Perfect calibration")
        ax.bar(
            [b.lower for b in non_empty],
            accs,
            width=1.0 / self._n_bins,
            align="edge",
            alpha=0.6,
            label="Model accuracy",
        )
        ax.plot(confs, accs, "o-", color="steelblue")
        ax.set_xlabel("Confidence")
        ax.set_ylabel("Accuracy")
        ax.set_title(f"{title}\nECE = {result.ece():.4f}")
        ax.legend()
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        plt.tight_layout()

        if save_path:
            plt.savefig(save_path)
            logger.info("Calibration plot saved to %s", save_path)
        else:
            plt.show()
