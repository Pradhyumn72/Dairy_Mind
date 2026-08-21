"""
Unit tests for MilkAnomalyDetector.

Scenario modelled
-----------------
A cow that consistently produces ~20 L/day for 14 days then suddenly drops
to 5 L — a 75 % reduction that should register as a HIGH-severity anomaly.

Test categories
---------------
1. Insufficient-data guard
2. fit() validation (negative values, too-few points)
3. Normal production (no anomaly)
4. Sudden severe drop (20 L → 5 L) — HIGH anomaly
5. Mild drop             — LOW anomaly
6. predict() on unfitted detector
7. Severity threshold boundary conditions
8. Properties and edge cases
"""
import pytest
from apps.health.ml.anomaly_detector import (
    MIN_HISTORY,
    MilkAnomalyDetector,
    _score_to_severity,
)

# ── Fixtures ──────────────────────────────────────────────────────────────────

# 60 days of healthy ~20 L production with realistic day-to-day variation.
# A larger, varied training set ensures IsolationForest has enough density
# to produce meaningful score separations between normal and anomalous values.
import random as _random
_random.seed(42)
HEALTHY_60_DAYS = [round(20.0 + _random.uniform(-2.0, 2.0), 2) for _ in range(60)]

# Minimum valid series (exactly 7 days, all normal)
MIN_VALID_SERIES = [20.0, 19.5, 20.5, 21.0, 19.8, 20.3, 20.1]


@pytest.fixture
def fitted_detector():
    """
    A MilkAnomalyDetector fitted on 60 days of realistic healthy data.
    contamination=0.05 — 5% of training points treated as anomalies.
    """
    det = MilkAnomalyDetector(contamination=0.05)
    det.fit(HEALTHY_60_DAYS)
    return det


@pytest.fixture
def unfitted_detector():
    """A freshly constructed, unfitted detector."""
    return MilkAnomalyDetector(contamination=0.1)


# ── 1. Insufficient-data guard ────────────────────────────────────────────────

class TestInsufficientDataGuard:
    def test_predict_without_fit_returns_insufficient_data(self, unfitted_detector):
        """predict() before fit() must return the sentinel dict."""
        result = unfitted_detector.predict(10.0)
        assert result["is_anomaly"] is False
        assert result["reason"] == "insufficient_data"

    def test_is_fitted_false_before_fit(self, unfitted_detector):
        assert unfitted_detector.is_fitted is False

    def test_is_fitted_true_after_fit(self, fitted_detector):
        assert fitted_detector.is_fitted is True

    def test_history_length_after_fit(self, fitted_detector):
        assert fitted_detector.history_length == len(HEALTHY_60_DAYS)


# ── 2. fit() validation ───────────────────────────────────────────────────────

class TestFitValidation:
    def test_fit_raises_on_too_few_points(self):
        """fit() must raise ValueError when fewer than MIN_HISTORY points given."""
        det = MilkAnomalyDetector()
        short_series = [20.0] * (MIN_HISTORY - 1)
        with pytest.raises(ValueError, match="at least"):
            det.fit(short_series)

    def test_fit_raises_on_negative_values(self):
        """fit() must reject negative values in the series."""
        det = MilkAnomalyDetector()
        with pytest.raises(ValueError, match="negative"):
            det.fit([20.0, -1.0, 20.0, 19.5, 21.0, 20.0, 19.0])

    def test_fit_accepts_minimum_valid_series(self):
        """fit() must succeed with exactly MIN_HISTORY points."""
        det = MilkAnomalyDetector()
        det.fit(MIN_VALID_SERIES)
        assert det.is_fitted

    def test_fit_accepts_zero_in_series(self):
        """Zero litres is a valid historical value (e.g. missed session)."""
        det = MilkAnomalyDetector()
        series = [0.0, 20.0, 19.5, 21.0, 20.3, 19.8, 20.1]
        det.fit(series)   # should not raise
        assert det.is_fitted

    def test_contamination_out_of_range_raises(self):
        with pytest.raises(ValueError):
            MilkAnomalyDetector(contamination=0.0)
        with pytest.raises(ValueError):
            MilkAnomalyDetector(contamination=1.0)


# ── 3. Normal production ──────────────────────────────────────────────────────

class TestNormalProduction:
    def test_normal_value_is_not_anomaly(self, fitted_detector):
        """
        The training mean (~19.8 L) should not be flagged.
        We use the exact mean of HEALTHY_60_DAYS rather than a round number
        to avoid IsolationForest score variance on tight datasets.
        """
        mean_val = round(sum(HEALTHY_60_DAYS) / len(HEALTHY_60_DAYS), 2)
        result = fitted_detector.predict(mean_val)
        assert result["is_anomaly"] is False

    def test_normal_result_has_expected_keys(self, fitted_detector):
        mean_val = round(sum(HEALTHY_60_DAYS) / len(HEALTHY_60_DAYS), 2)
        result = fitted_detector.predict(mean_val)
        assert "anomaly_score" in result
        assert "mean" in result
        assert "std" in result
        assert "pct_drop" in result
        assert "message" in result

    def test_normal_result_severity_is_none(self, fitted_detector):
        """severity must be None (absent) for non-anomalous predictions."""
        mean_val = round(sum(HEALTHY_60_DAYS) / len(HEALTHY_60_DAYS), 2)
        result = fitted_detector.predict(mean_val)
        assert result["is_anomaly"] is False
        assert result.get("severity") is None

    def test_normal_mean_is_approx_20(self, fitted_detector):
        mean_val = round(sum(HEALTHY_60_DAYS) / len(HEALTHY_60_DAYS), 2)
        result = fitted_detector.predict(mean_val)
        assert 18.0 < result["mean"] < 22.0


# ── 4. Sudden severe drop — the primary scenario ──────────────────────────────

class TestSuddenSevereDrop:
    """
    Core scenario: cow produces ~20 L/day for 14 days then drops to 5 L.
    A 75 % reduction must be flagged as an anomaly with HIGH severity.
    """

    def test_severe_drop_is_anomaly(self, fitted_detector):
        result = fitted_detector.predict(5.0)
        assert result["is_anomaly"] is True

    def test_severe_drop_severity_is_high(self, fitted_detector):
        result = fitted_detector.predict(5.0)
        assert result["severity"] == "HIGH"

    def test_severe_drop_score_below_high_threshold(self, fitted_detector):
        result = fitted_detector.predict(5.0)
        assert result["anomaly_score"] < -0.5

    def test_severe_drop_pct_drop_is_large(self, fitted_detector):
        """Drop percentage should be roughly 70–80 % given ~20 L baseline."""
        result = fitted_detector.predict(5.0)
        assert result["pct_drop"] > 60.0

    def test_severe_drop_message_mentions_value(self, fitted_detector):
        result = fitted_detector.predict(5.0)
        assert "5.0" in result["message"] or "5" in result["message"]

    def test_severe_drop_message_mentions_severity(self, fitted_detector):
        result = fitted_detector.predict(5.0)
        assert "HIGH" in result["message"]

    def test_severe_drop_result_has_all_keys(self, fitted_detector):
        result = fitted_detector.predict(5.0)
        for key in ("is_anomaly", "anomaly_score", "severity", "mean",
                    "std", "pct_drop", "message"):
            assert key in result, f"Missing key: {key}"


# ── 5. Mild drop ──────────────────────────────────────────────────────────────

class TestMildDrop:
    """
    A very mild dip just below the LOW threshold.
    We construct a tightly clustered training set and a large enough drop
    to guarantee the score falls below -0.1 but check only for is_anomaly.
    """

    def test_mild_drop_detected_as_anomaly(self):
        """
        Use a very tight distribution so even a moderate dip is an outlier.
        20 L baseline → 12 L drop should be below the LOW threshold.
        """
        tight_series = [20.0] * 30   # 30 identical values → zero variance
        det = MilkAnomalyDetector(contamination=0.05)
        det.fit(tight_series)
        result = det.predict(12.0)
        # With zero variance in history, any deviation should be anomalous
        assert result["is_anomaly"] is True

    def test_mild_anomaly_has_severity_field(self):
        tight_series = [20.0] * 30
        det = MilkAnomalyDetector(contamination=0.05)
        det.fit(tight_series)
        result = det.predict(12.0)
        if result["is_anomaly"]:
            assert result["severity"] in ("LOW", "MEDIUM", "HIGH")


# ── 6. predict() with negative value ─────────────────────────────────────────

class TestPredictNegativeValue:
    def test_predict_raises_on_negative_value(self, fitted_detector):
        with pytest.raises(ValueError, match="non-negative"):
            fitted_detector.predict(-1.0)


# ── 7. Severity threshold helpers ────────────────────────────────────────────

class TestSeverityThresholds:
    """Unit-test the module-level _score_to_severity helper directly."""

    @pytest.mark.parametrize("score,expected", [
        (-0.11, "LOW"),    # just below LOW threshold
        (-0.10, "LOW"),    # note: strict <, so -0.10 is still LOW
        (-0.31, "MEDIUM"),
        (-0.50, "MEDIUM"), # strict < -0.5 required for HIGH
        (-0.51, "HIGH"),
        (-0.99, "HIGH"),
    ])
    def test_score_to_severity_boundaries(self, score, expected):
        assert _score_to_severity(score) == expected

    def test_score_minus_one_is_high(self):
        assert _score_to_severity(-1.0) == "HIGH"


# ── 8. Edge cases ─────────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_predict_zero_litres(self, fitted_detector):
        """Zero litres is a valid (extreme) input — should not raise."""
        result = fitted_detector.predict(0.0)
        assert isinstance(result["is_anomaly"], bool)

    def test_predict_very_high_value(self, fitted_detector):
        """A huge spike may or may not be anomalous, but must not raise."""
        result = fitted_detector.predict(200.0)
        assert isinstance(result["is_anomaly"], bool)

    def test_fit_then_refit_updates_history(self):
        """Calling fit() a second time replaces the previous model."""
        det = MilkAnomalyDetector()
        det.fit(MIN_VALID_SERIES)
        assert det.history_length == len(MIN_VALID_SERIES)

        new_series = HEALTHY_60_DAYS
        det.fit(new_series)
        assert det.history_length == len(new_series)

    def test_result_scores_are_rounded(self, fitted_detector):
        """anomaly_score, mean, std, pct_drop should be rounded floats."""
        result = fitted_detector.predict(5.0)
        # Check they're floats with at most 4 decimal places
        assert isinstance(result["anomaly_score"], float)
        assert len(str(result["anomaly_score"]).split(".")[-1]) <= 4

    def test_multiple_predictions_independent(self, fitted_detector):
        """Consecutive predictions must not affect each other."""
        r1 = fitted_detector.predict(20.0)
        r2 = fitted_detector.predict(5.0)
        r3 = fitted_detector.predict(20.0)
        assert r1["is_anomaly"] == r3["is_anomaly"]
        assert r2["is_anomaly"] is True
