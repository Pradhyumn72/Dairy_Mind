"""
ml/anomaly_detection.py
~~~~~~~~~~~~~~~~~~~~~~~

IsolationForestModel — project-root ML module as defined in the spec.

This is a thin wrapper around apps.health.ml.MilkAnomalyDetector that
exposes the interface described in Requirement 10 (ML Model Integration Points):

    class IsolationForestModel:
        def train(self, animal_id, yield_series) -> None
        def predict(self, animal_id, yield_value) -> dict
        def save_model(self, animal_id) -> None
        def load_model(self, animal_id) -> None

Usage
-----
    from ml.anomaly_detection import IsolationForestModel

    model = IsolationForestModel()
    model.train(animal_id=7, yield_series=[18.5, 20.1, 19.8, ...])
    result = model.predict(animal_id=7, yield_value=5.0)
    # result = {
    #   "is_anomaly": True,
    #   "anomaly_score": -0.62,
    #   "severity": "HIGH",
    #   ...
    # }
"""
import logging
from apps.health.ml.anomaly_detector import MilkAnomalyDetector

logger = logging.getLogger(__name__)

# In-memory store of fitted detector instances keyed by animal_id.
# In production this would be replaced by a persistent model store (e.g. joblib files).
_model_registry: dict[int, MilkAnomalyDetector] = {}


class IsolationForestModel:
    """
    Project-level Isolation Forest wrapper.

    Maintains one MilkAnomalyDetector per animal_id so models can be
    trained, saved, and loaded independently for each cattle.
    """

    def __init__(self, contamination: float = 0.1) -> None:
        self._contamination = contamination

    # ── Spec-defined interface ────────────────────────────────────────────────

    def train(self, animal_id: int, yield_series: list[float]) -> None:
        """
        Train (or re-train) the model for *animal_id* on *yield_series*.

        Parameters
        ----------
        animal_id    : int
        yield_series : list[float] — ordered daily total-litres values
        """
        detector = MilkAnomalyDetector(contamination=self._contamination)
        detector.fit(yield_series)
        _model_registry[animal_id] = detector
        logger.info("IsolationForestModel trained for animal_id=%d (%d points)", animal_id, len(yield_series))

    def predict(self, animal_id: int, yield_value: float) -> dict:
        """
        Score *yield_value* for *animal_id*.

        Returns the same dict shape as MilkAnomalyDetector.predict().
        If no model is trained for this animal, returns insufficient_data.
        """
        detector = _model_registry.get(animal_id)
        if detector is None:
            return {"is_anomaly": False, "reason": "insufficient_data"}
        return detector.predict(yield_value)

    def save_model(self, animal_id: int) -> None:
        """
        Persist the trained model for *animal_id* to disk using joblib.

        Falls back to a no-op with a warning if joblib is unavailable.
        """
        detector = _model_registry.get(animal_id)
        if detector is None:
            logger.warning("save_model: no model for animal_id=%d", animal_id)
            return
        try:
            import joblib, os
            path = f"/tmp/dairymind_model_{animal_id}.joblib"
            joblib.dump(detector, path)
            logger.info("Model saved for animal_id=%d → %s", animal_id, path)
        except ImportError:
            logger.warning("joblib not available — model for animal_id=%d not persisted", animal_id)

    def load_model(self, animal_id: int) -> None:
        """
        Load a previously persisted model for *animal_id* from disk.

        No-op if the file does not exist.
        """
        try:
            import joblib
            path = f"/tmp/dairymind_model_{animal_id}.joblib"
            if not __import__("os").path.exists(path):
                logger.debug("No saved model file for animal_id=%d", animal_id)
                return
            _model_registry[animal_id] = joblib.load(path)
            logger.info("Model loaded for animal_id=%d from %s", animal_id, path)
        except ImportError:
            logger.warning("joblib not available — cannot load model for animal_id=%d", animal_id)
