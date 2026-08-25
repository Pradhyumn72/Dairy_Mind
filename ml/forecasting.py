"""
ml/forecasting.py
~~~~~~~~~~~~~~~~~

ProphetForecaster — project-root ML module as defined in the spec.

Exposes the interface from Requirement 10 (ML Model Integration Points):

    class ProphetForecaster:
        def fit(self, animal_id, date_yield_series) -> None   # [{ds, y}]
        def predict(self, animal_id, periods=30) -> list[dict] # [{ds, yhat, yhat_lower, yhat_upper}]

Usage
-----
    from ml.forecasting import ProphetForecaster

    forecaster = ProphetForecaster()
    forecaster.fit(animal_id=3, date_yield_series=[
        {"ds": "2025-01-01", "y": 18.5},
        ...
    ])
    rows = forecaster.predict(animal_id=3, periods=30)
    # rows = [{"ds": "2025-04-01", "yhat": 19.2, "yhat_lower": 17.1, "yhat_upper": 21.3}, ...]
"""
import logging
import pandas as pd
from apps.forecast.ml.production_forecaster import MilkProductionForecaster

logger = logging.getLogger(__name__)

# In-memory store of fitted Prophet models keyed by animal_id
_fitted_models: dict[int, object] = {}   # stores Prophet model instances


class ProphetForecaster:
    """
    Project-level Prophet wrapper.

    Provides a stateful fit/predict interface so models can be fitted once
    and used multiple times without re-training.
    """

    def fit(self, animal_id: int, date_yield_series: list[dict]) -> None:
        """
        Fit a Prophet model for *animal_id*.

        Parameters
        ----------
        animal_id         : int
        date_yield_series : list[dict] — each dict has keys ``ds`` (date str) and ``y`` (float)
        """
        if len(date_yield_series) < 30:
            logger.warning("ProphetForecaster.fit: only %d records for animal_id=%d (need ≥30)", len(date_yield_series), animal_id)

        df = pd.DataFrame(date_yield_series)
        df["ds"] = pd.to_datetime(df["ds"])
        df["y"]  = df["y"].astype(float)

        # Build and fit Prophet model
        forecaster = MilkProductionForecaster()
        model = forecaster._build_model()
        model.fit(df)
        _fitted_models[animal_id] = model
        logger.info("ProphetForecaster fitted for animal_id=%d (%d rows)", animal_id, len(df))

    def predict(self, animal_id: int, periods: int = 30) -> list[dict]:
        """
        Generate a *periods*-day forecast for *animal_id*.

        Returns
        -------
        list[dict] — each dict has keys: ds, yhat, yhat_lower, yhat_upper
        """
        model = _fitted_models.get(animal_id)
        if model is None:
            logger.warning("ProphetForecaster.predict: no fitted model for animal_id=%d", animal_id)
            return []

        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            future   = model.make_future_dataframe(periods=periods, freq="D")
            forecast = model.predict(future)

        result_df = forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(periods)
        result_df["yhat_lower"] = result_df["yhat_lower"].clip(lower=0.0)
        result_df["yhat"]       = result_df["yhat"].clip(lower=0.0)

        return [
            {
                "ds":         row["ds"].strftime("%Y-%m-%d"),
                "yhat":       round(float(row["yhat"]),       2),
                "yhat_lower": round(float(row["yhat_lower"]), 2),
                "yhat_upper": round(float(row["yhat_upper"]), 2),
            }
            for _, row in result_df.iterrows()
        ]
