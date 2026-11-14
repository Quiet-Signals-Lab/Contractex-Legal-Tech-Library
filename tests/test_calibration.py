"""CalibrationAnalyzer: reliability bins and Expected Calibration Error."""

from __future__ import annotations

import pytest

from contractex.eval import CalibrationAnalyzer


def ece(pairs: list[tuple[float, bool]]) -> float:
    analyzer = CalibrationAnalyzer()
    analyzer.add_batch(pairs)
    return analyzer.analyze().ece()


class TestECE:
    def test_empty(self):
        assert CalibrationAnalyzer().analyze().ece() == 0.0

    @pytest.mark.parametrize(
        "pairs",
        [
            [(1.0, True)] * 10,
            [(0.0, False)] * 10,
            [(0.9, True)] * 9 + [(0.9, False)],
            [(0.5, True), (0.5, False)],
        ],
    )
    def test_perfectly_calibrated_scores_zero(self, pairs):
        assert ece(pairs) == pytest.approx(0.0)

    def test_overconfident(self):
        # 0.9 confidence, 50% correct: off by 0.4
        assert ece([(0.9, True), (0.9, False)]) == pytest.approx(0.4)

    def test_bin_uses_the_mean_of_its_samples(self):
        analyzer = CalibrationAnalyzer()
        analyzer.add_batch([(0.91, True), (0.99, True)])
        (b,) = [b for b in analyzer.analyze().bins if b.count]
        assert (b.lower, b.count) == (pytest.approx(0.9), 2)
        assert b.mean_confidence == pytest.approx(0.95)

    def test_edge_values_land_in_first_and_last_bin(self):
        analyzer = CalibrationAnalyzer()
        analyzer.add_batch([(0.0, False), (1.0, True)])
        bins = analyzer.analyze().bins
        assert (bins[0].count, bins[-1].count) == (1, 1)


class TestValidation:
    @pytest.mark.parametrize("confidence", [-0.3, 1.01, float("nan")])
    def test_confidence_outside_unit_interval_is_rejected(self, confidence):
        with pytest.raises(ValueError, match="confidence"):
            CalibrationAnalyzer().add(confidence, True)

    def test_add_batch_validates_too(self):
        with pytest.raises(ValueError, match="confidence"):
            CalibrationAnalyzer().add_batch([(0.5, True), (1.5, True)])
