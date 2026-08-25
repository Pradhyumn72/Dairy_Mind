"""
health/ml/anomaly_detector.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MilkAnomalyDetector — wraps scikit-learn IsolationForest to detect
abnormal daily milk production for a single cattle.

Usage
-----
    from apps.health.ml import MilkAnomalyDetector

    detector = MilkAnomalyDetector()
    detector.fit([18.5, 20.1, 19.8, 21.0, 20.5, 19.9, 20.3])
    result = detector.predict(5.0)
    # {"is_anomaly": True, "anomaly_score": -0.62, "severity": "HIGH", ...}
"""
import logging
import statistics

import numpy as np
from sklearn.ensemble import IsolationForest

logger = logging.getLogger(__name__)

# ── Severity thresholds ───────────────────────────────────────────────────────
THRESHOLD_LOW    = -0.1
THRESHOLD_MEDIUM = -0.3
THRESHOLD_HIGH   = -0.5
MIN_HISTORY      = 7      # minimum days required to fit the model

# Fallback string on API / model error
FALLBACK_SUMMARY = "Summary unavailable. Please review the original report."


def _score_to_severity(score: float) -> str:
    if score < THRESHOLD_HIGH:
        return "HIGH"
    if score < THRESHOLD_MEDIUM:
        return "MEDIUM"
    return "LOW"


class MilkAnomalyDetector:
    """
    Anomaly detector for daily milk production using IsolationForest.

    Parameters
    ----------
    contamination : float  Expected fraction of anomalies (default 0.1)
    """

    def __init__(self, contamination: float = 0.1) -> None:
        if not (0 < contamination < 1):
            raise ValueError("contamination must be in (0, 1).")
        self._contamination = contamination
        self._model: IsolationForest | None = None
        self._is_fitted = False
        self._history: list[float] = []

    # ── Public API ────────────────────────────────────────────────────────────

    def fit(self, milk_series: list[float]) -> None:
        """
        Train on historical daily milk totals.

        Parameters
        ----------
        milk_series : list[float]  Ordered daily total-litres values.
                                   Must contain at least MIN_HISTORY entries.
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
            "MilkAnomalyDetector fitted on %d points (mean=%.2f, contamination=%.2f)",
            len(milk_series), statistics.mean(milk_series), self._contamination,
        )

    def predict(self, value: float) -> dict:
        """
        Score a single daily milk production value.

        Returns
        -------
        dict
            Insufficient data:
                {"is_anomaly": False, "reason": "insufficient_data"}
            Normal production:
                {"is_anomaly": False, "anomaly_score": float, "severity": None,
                 "mean": float, "std": float, "pct_drop": float, "message": str}
            Anomaly:
                {"is_anomaly": True, "anomaly_score": float, "severity": "LOW"|"MEDIUM"|"HIGH",
                 "mean": float, "std": float, "pct_drop": float, "message": str}
        """
        if not self._is_fitted:
            return {"is_anomaly": False, "reason": "insufficient_data"}

        if value < 0:
            raise ValueError("value must be non-negative.")

        score = float(
            self._model.score_samples(np.array([[value]], dtype=float))[0]
        )
        mean     = statistics.mean(self._history)
        std      = statistics.pstdev(self._history) if len(self._history) > 1 else 0.0
        pct_drop = ((mean - value) / mean * 100) if mean > 0 else 0.0

        is_anomaly = score < THRESHOLD_LOW

        if not is_anomaly:
            return {
                "is_anomaly":    False,
                "anomaly_score": round(score, 4),
                "severity":      None,
                "mean":          round(mean, 2),
                "std":           round(std, 2),
                "pct_drop":      round(pct_drop, 1),
                "message":       f"Production ({value:.1f} L) is within normal range (avg: {mean:.1f} L).",
            }

        severity = _score_to_severity(score)
        message  = (
            f"Anomalous milk production detected: {value:.1f} L "
            f"(avg: {mean:.1f} L, drop: {pct_drop:.0f}%). "
            f"Score: {score:.3f}. Severity: {severity}."
        )
        logger.warning(
            "Anomaly detected: value=%.2f mean=%.2f score=%.4f severity=%s",
            value, mean, score, severity,
        )
        return {
            "is_anomaly":    True,
            "anomaly_score": round(score, 4),
            "severity":      severity,
            "mean":          round(mean, 2),
            "std":           round(std, 2),
            "pct_drop":      round(pct_drop, 1),
            "message":       message,
        }

    @property
    def is_fitted(self) -> bool:
        return self._is_fitted

    @property
    def history_length(self) -> int:
        return len(self._history)
