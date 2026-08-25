"""
DairyMind top-level ML module.

Re-exports the three main ML classes from their app-level implementations
so they can be imported from either location:

    from ml import IsolationForestModel, ProphetForecaster, BreedingSuccessModel
    # or
    from apps.health.ml import MilkAnomalyDetector
"""
from apps.health.ml.anomaly_detector import MilkAnomalyDetector as IsolationForestModel
from apps.forecast.ml.production_forecaster import MilkProductionForecaster as ProphetForecaster
from apps.breeding.ml.breeding_predictor import BreedingPredictor as BreedingSuccessModel

__all__ = ["IsolationForestModel", "ProphetForecaster", "BreedingSuccessModel"]
