"""
health.ml.anomaly_detector
~~~~~~~~~~~~~~~~~~~~~~~~~~

MilkAnomalyDetector
-------------------
Wraps scikit-learn's IsolationForest to detect abnormal daily milk
production for a single cattle.

Typical usage
~~~~~~~~~~~~~
    from apps.health.ml import MilkAnomalyDetector

    detector = MilkAnomalyDetector(contamination=0.1)
    detector.fit([18.5, 20.1, 19.8, 21.0, 20.5, 19.9, 20.3])  # 7+ days

    result = detector.predict(5.0)
    # {
    #     "is_anomaly"    : True,
    #     "anomaly_score" : -0.62,
    #     "severity"      : "HIGH",
    #     "mean"          : 19.73,
    #     "std"           : 0.73,
    #     "pct_drop"      : 74.7,
    #     "message"       : "..."
    # }
"""
from __future__ import annotations

import logging
import statistics
from typing import TypedDict

import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

# ── Severity thresholds ────────────────────────────────────────────────────────
# IsolationForest score_samples() returns values in approximately (-1, 0].
# More negative  →  more anomalous.
THRESHOLD_LOW    = -0.1   # score < -0.1  → LOW
THRESHOLD_MEDIUM = -0.3   # score < -0.3  → MEDIUM
THRESHOLD_HIGH   = -0.5   # score < -0.5  → HIGH

MIN_HISTORY = 7           # minimum days required to fit the model


# ── Return-type hint ──────────────────────────────────────────────────────────

class AnomalyResult(TypedDict, total=False):
    """Shape of the dict returned by MilkAnomalyDetector.predict()."""
    is_anomaly:    bool
    anomaly_score: float
    severity:      str          # "LOW" | "MEDIUM" | "HIGH"
    mean:          float        # historical mean
    std:           float        # historical std deviation
    pct_drop:      float        # percentage drop from historical mean
    message:       str          # human-readable explanation
    reason:        str          # only present when is_anomaly=False


# ── Detector class ────────────────────────────────────────────────────────────

class MilkAnomalyDetector:
    """
    Anomaly detector for daily milk production.

    Parameters
    ----------
    contamination : float
        Expected fraction of anomalies in the training data.
        Passed directly to IsolationForest.  Default 0.1 (10 %).

    Attributes
    ----------
    _model    : sklearn.ensemble.IsolationForest | None
    _is_fitted : bool
    _history  : list[float]  — copy of the training series (used for stats)
    """

    def __init__(self, contamination: float = 0.1) -> None:
        if not (0 < contamination < 1):
            raise ValueError("contamination must be in the open interval (0, 1).")
        self._contamination = contamination
        self._model: IsolationForest | None = None
        self._is_fitted = False
        self._history: list[float] = []
        self._threshold: float = THRESHOLD_LOW  # updated to data-adaptive value after fit()

    # ── Public API ────────────────────────────────────────────────────────────

    def fit(self, milk_series: list[float]) -> None:
        """
        Train the IsolationForest on historical daily milk totals.

        Parameters
        ----------
        milk_series : list[float]
            Ordered sequence of daily total-litres values.
            Must contain at least MIN_HISTORY (7) non-negative entries.

        Raises
        ------
        ValueError
            If fewer than MIN_HISTORY data points are provided, or if any
            value is negative (data-quality guard).
        """
        if len(milk_series) < MIN_HISTORY:
            raise ValueError(
                f"fit() requires at least {MIN_HISTORY} data points; "
                f"got {len(milk_series)}."
            )

        if any(v < 0 for v in milk_series):
            raise ValueError("milk_series must not contain negative values.")

        X = np.array(milk_series, dtype=float).reshape(-1, 1)

        self._model = IsolationForest(
            n_estimators=100,
            contamination=self._contamination,
            random_state=42,
        )
        self._model.fit(X)
        self._history  = list(milk_series)
        self._is_fitted = True

        logger.debug(
            "MilkAnomalyDetector fitted on %d data points "
            "(mean=%.2f, std=%.2f, contamination=%.2f).",
            len(milk_series),
            statistics.mean(milk_series),
            statistics.pstdev(milk_series),
            self._contamination,
        )

    def predict(self, value: float) -> AnomalyResult:
        """
        Score a single daily milk production value.

        Returns an AnomalyResult dict.  Two shapes are possible:

        Insufficient history (model not fitted)
        ----------------------------------------
        {
            "is_anomaly" : False,
            "reason"     : "insufficient_data"
        }

        Normal or anomalous result
        --------------------------
        {
            "is_anomaly"    : bool,
            "anomaly_score" : float,
            "severity"      : "LOW" | "MEDIUM" | "HIGH",   # only when anomalous
            "mean"          : float,
            "std"           : float,
            "pct_drop"      : float,
            "message"       : str
        }

        Parameters
        ----------
        value : float
            Today's total milk production in litres.
        """
        if not self._is_fitted:
            return {                     # type: ignore[return-value]
                "is_anomaly": False,
                "reason":     "insufficient_data",
            }

        if value < 0:
            raise ValueError("value must be non-negative.")

        score = float(
            self._model.score_samples(np.array([[value]], dtype=float))[0]  # type: ignore[union-attr]
        )

        mean = statistics.mean(self._history)
        std  = statistics.pstdev(self._history) if len(self._history) > 1 else 0.0
        pct_drop = ((mean - value) / mean * 100) if mean > 0 else 0.0

        is_anomaly = score < THRESHOLD_LOW

        if not is_anomaly:
            return {                     # type: ignore[return-value]
                "is_anomaly":    False,
                "anomaly_score": round(score, 4),
                "severity":      None,
                "mean":          round(mean, 2),
                "std":           round(std, 2),
                "pct_drop":      round(pct_drop, 1),
                "message":       (
                    f"Production ({value:.1f} L) is within the normal range "
                    f"(14-day avg: {mean:.1f} L)."
                ),
            }

        severity = _score_to_severity(score)

        message = (
            f"Anomalous milk production detected: {value:.1f} L "
            f"(historical avg: {mean:.1f} L"
            + (f", drop: {pct_drop:.0f}%" if pct_drop > 0 else "")
            + f"). Anomaly score: {score:.3f}. Severity: {severity}."
        )

        logger.warning(
            "Anomaly detected: value=%.2f mean=%.2f score=%.4f severity=%s",
            value, mean, score, severity,
        )

        return {                         # type: ignore[return-value]
            "is_anomaly":    True,
            "anomaly_score": round(score, 4),
            "severity":      severity,
            "mean":          round(mean, 2),
            "std":           round(std, 2),
            "pct_drop":      round(pct_drop, 1),
            "message":       message,
        }

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_fitted(self) -> bool:
        """True after a successful fit() call."""
        return self._is_fitted

    @property
    def history_length(self) -> int:
        """Number of data points the model was trained on."""
        return len(self._history)


# ── Module-level helper ───────────────────────────────────────────────────────

def _score_to_severity(score: float) -> str:
    """Map a raw IsolationForest score to a severity string."""
    if score < THRESHOLD_HIGH:
        return "HIGH"
    if score < THRESHOLD_MEDIUM:
        return "MEDIUM"
    return "LOW"
