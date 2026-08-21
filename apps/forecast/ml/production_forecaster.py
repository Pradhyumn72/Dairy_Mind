"""
forecast.ml.production_forecaster
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MilkProductionForecaster
------------------------
Wraps Facebook Prophet to generate per-cattle daily milk-production forecasts
from historical MilkLog data stored in the Django database.

Typical usage
~~~~~~~~~~~~~
    from apps.forecast.ml import MilkProductionForecaster

    forecaster = MilkProductionForecaster()
    df = forecaster.fit_and_forecast(cattle_id=7, days_history=90, forecast_days=30)

    # df columns: ds (datetime64), yhat, yhat_lower, yhat_upper (float64)
    # Only the forward-looking rows are returned (future dates only).

Design notes
~~~~~~~~~~~~
* Prophet requires a DataFrame with columns ``ds`` (datestamp) and ``y`` (value).
* We add **weekly** seasonality (period=7) to capture Mon–Sun milking patterns,
  and **yearly** seasonality (period=365.25) for seasonal trends.
* Built-in daily seasonality is disabled — daily milk is already one row/day so
  there is nothing intra-day to model.
* The method is **stateless**: no model is persisted to disk.  The caller (view
  or Celery task) is responsible for saving results to ``ProductionForecast``.
* Suppresses Prophet's verbose Stan output via logging redirect.
"""
from __future__ import annotations

import logging
import warnings
from datetime import date, timedelta
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    pass  # Prophet import is deferred to avoid slow startup time

logger = logging.getLogger(__name__)

# Minimum number of historical MilkLog records required for a reliable forecast
MIN_HISTORY_DAYS = 30


class InsufficientDataError(Exception):
    """
    Raised by fit_and_forecast() when fewer than MIN_HISTORY_DAYS records
    are available for the requested cattle.

    Attributes
    ----------
    cattle_id     : int
    available     : int  — number of records actually found
    required      : int  — MIN_HISTORY_DAYS
    """

    def __init__(self, cattle_id: int, available: int, required: int = MIN_HISTORY_DAYS):
        self.cattle_id = cattle_id
        self.available = available
        self.required  = required
        super().__init__(
            f"Cattle {cattle_id} has only {available} day(s) of MilkLog data. "
            f"At least {required} days are required to generate a reliable forecast. "
            "Please add more milk production records before requesting a forecast."
        )


class MilkProductionForecaster:
    """
    Generates a Prophet-based 30-day milk production forecast for a single cattle.

    Parameters
    ----------
    (none — instantiation is cheap; all heavy work happens in fit_and_forecast)

    Methods
    -------
    fit_and_forecast(cattle_id, days_history, forecast_days) → pd.DataFrame
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def fit_and_forecast(
        self,
        cattle_id: int,
        days_history: int = 90,
        forecast_days: int = 30,
    ) -> pd.DataFrame:
        """
        Fetch historical MilkLogs, fit Prophet, and return a forecast DataFrame.

        Parameters
        ----------
        cattle_id     : int   — PK of the Cattle record
        days_history  : int   — how many recent days to include in training
                                (default 90; capped at all available records)
        forecast_days : int   — how many future days to forecast (default 30)

        Returns
        -------
        pd.DataFrame with columns:
            ds          : datetime64[ns]  — forecast date
            yhat        : float64         — predicted daily litres
            yhat_lower  : float64         — 80% CI lower bound
            yhat_upper  : float64         — 80% CI upper bound

        Only **future** rows (ds > today) are returned — Prophet output for
        historical dates is discarded.

        Raises
        ------
        InsufficientDataError
            When the cattle has fewer than MIN_HISTORY_DAYS MilkLog records.
        django.core.exceptions.ObjectDoesNotExist
            When no Cattle with the given PK exists (bubbles up from ORM).
        """
        logger.info(
            "[MilkProductionForecaster] Starting forecast for cattle_id=%d "
            "(days_history=%d, forecast_days=%d)",
            cattle_id, days_history, forecast_days,
        )

        # ── Step 1: Fetch history from DB ─────────────────────────────────────
        history_df = self._fetch_history(cattle_id, days_history)

        if len(history_df) < MIN_HISTORY_DAYS:
            raise InsufficientDataError(
                cattle_id=cattle_id,
                available=len(history_df),
            )

        # ── Step 2: Fit Prophet ───────────────────────────────────────────────
        model = self._build_model()
        model.fit(history_df)

        logger.info(
            "[MilkProductionForecaster] Prophet fitted on %d rows for cattle_id=%d",
            len(history_df), cattle_id,
        )

        # ── Step 3: Make future DataFrame and predict ─────────────────────────
        # total_periods = history + forecast so Prophet has context; we keep only future
        future = model.make_future_dataframe(periods=forecast_days, freq="D")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            forecast = model.predict(future)

        # ── Step 4: Filter to future rows only ────────────────────────────────
        today = pd.Timestamp(date.today())
        result = (
            forecast[forecast["ds"] > today][["ds", "yhat", "yhat_lower", "yhat_upper"]]
            .head(forecast_days)  # exact window
            .reset_index(drop=True)
        )

        # Clamp negative lower bounds to 0 (physically impossible yield)
        result["yhat_lower"] = result["yhat_lower"].clip(lower=0.0)
        result["yhat"]       = result["yhat"].clip(lower=0.0)

        logger.info(
            "[MilkProductionForecaster] Forecast complete: %d rows, "
            "cattle_id=%d, range %s → %s",
            len(result),
            cattle_id,
            result["ds"].iloc[0].date() if len(result) else "N/A",
            result["ds"].iloc[-1].date() if len(result) else "N/A",
        )

        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _fetch_history(cattle_id: int, days_history: int) -> pd.DataFrame:
        """
        Query MilkLog records for *cattle_id* over the last *days_history* days
        and return a Prophet-compatible DataFrame with columns ``ds`` and ``y``.

        Gaps (days with no log) are filled with the rolling 7-day mean to reduce
        Prophet's sensitivity to missing data without introducing hard zeros.
        """
        from apps.milk.models import MilkLog

        cutoff = date.today() - timedelta(days=days_history)
        logs = (
            MilkLog.objects
            .filter(cattle_id=cattle_id, date__gte=cutoff)
            .order_by("date")
            .values_list("date", "total_litres")
        )

        if not logs:
            return pd.DataFrame(columns=["ds", "y"])

        df = pd.DataFrame(list(logs), columns=["ds", "y"])
        df["ds"] = pd.to_datetime(df["ds"])
        df["y"]  = df["y"].astype(float)

        # Fill date gaps so Prophet receives a contiguous series
        date_range = pd.date_range(df["ds"].min(), df["ds"].max(), freq="D")
        df = df.set_index("ds").reindex(date_range).rename_axis("ds").reset_index()

        # Fill gaps with a 7-day rolling mean (forward + backward fill for edges)
        df["y"] = (
            df["y"]
            .fillna(df["y"].rolling(7, min_periods=1, center=True).mean())
            .ffill()
            .bfill()
            .clip(lower=0.0)
        )

        return df

    @staticmethod
    def _build_model():
        """
        Construct a Prophet model with weekly + yearly seasonality.

        Daily seasonality is disabled — each row already represents one day.
        Verbose Stan output is suppressed.
        """
        # Deferred import to avoid slowing down Django startup
        from prophet import Prophet  # type: ignore[import-untyped]
        import logging as _logging

        # Silence Prophet / cmdstanpy noise
        _logging.getLogger("prophet").setLevel(_logging.WARNING)
        _logging.getLogger("cmdstanpy").setLevel(_logging.WARNING)

        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=True,
            yearly_seasonality=True,
            interval_width=0.80,          # 80% confidence interval
            uncertainty_samples=200,      # faster than the default 1000
        )
        return model
