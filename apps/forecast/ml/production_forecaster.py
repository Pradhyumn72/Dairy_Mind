"""
forecast/ml/production_forecaster.py
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

MilkProductionForecaster — progressive tiered forecasting based on available
milk log history.  Four tiers replace the old hard 30-day minimum:

  Tier 1  1-6 days    flat-average projection,        3 days ahead,  VERY_LOW
  Tier 2  7-13 days   linear-regression trend,        7 days ahead,  LOW
  Tier 3  14-29 days  Prophet (weekly only),          14 days ahead, MEDIUM
  Tier 4  30+ days    Prophet (weekly + yearly),      30 days ahead, HIGH

Usage
-----
    from apps.forecast.ml import MilkProductionForecaster

    forecaster = MilkProductionForecaster()
    result = forecaster.fit_and_forecast(cattle_id=7)
    # result.df       → pd.DataFrame  columns: ds, yhat, yhat_lower, yhat_upper
    # result.tier     → int  1-4
    # result.confidence → str
    # result.message  → str | None
    # result.days_of_data_available → int
"""
import logging
import warnings
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


# ── Tier thresholds ───────────────────────────────────────────────────────────

TIER1_MAX =  6   # 1-6  days
TIER2_MAX = 13   # 7-13 days
TIER3_MAX = 29   # 14-29 days
# 30+           → Tier 4


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class ForecastResult:
    """Returned by MilkProductionForecaster.fit_and_forecast()."""
    df: pd.DataFrame                 # columns: ds, yhat, yhat_lower, yhat_upper
    tier: int                        # 1 | 2 | 3 | 4
    confidence: str                  # VERY_LOW | LOW | MEDIUM | HIGH
    message: Optional[str]           # tier-specific guidance, None for Tier 4
    days_of_data_available: int      # actual distinct days of MilkLog data


# ── Legacy exception kept for backward-compat (tasks.py catches it) ──────────

class InsufficientDataError(Exception):
    """Raised only when days_of_data_available == 0 (truly no logs at all)."""
    def __init__(self, cattle_id: int, available: int = 0):
        self.cattle_id = cattle_id
        self.available = available
        self.required  = 1
        super().__init__(
            f"Cattle {cattle_id} has no milk log data. "
            "Add at least one milk log to generate a forecast."
        )


# ── Forecaster ────────────────────────────────────────────────────────────────

class MilkProductionForecaster:
    """
    Progressive tiered milk production forecaster.

    Methods
    -------
    fit_and_forecast(cattle_id, days_history=90) → ForecastResult
    """

    def fit_and_forecast(
        self,
        cattle_id: int,
        days_history: int = 90,
        forecast_days: Optional[int] = None,   # overrides tier default when set
    ) -> ForecastResult:
        """
        Fetch MilkLogs, pick the appropriate tier, return a ForecastResult.

        Parameters
        ----------
        cattle_id     : int
        days_history  : int   Days of history window for training (default 90).
                              For Tiers 1-2 ALL available data is used regardless.
        forecast_days : int | None
                              Override the tier's default horizon (optional).

        Returns
        -------
        ForecastResult

        Raises
        ------
        InsufficientDataError   when the cattle has literally zero milk logs.
        """
        logger.info(
            "[MilkProductionForecaster] cattle_id=%d days_history=%d",
            cattle_id, days_history,
        )

        # ── Count ALL available distinct days of data ─────────────────────────
        days_available = self._count_available_days(cattle_id)

        if days_available == 0:
            raise InsufficientDataError(cattle_id=cattle_id, available=0)

        # ── Pick tier ─────────────────────────────────────────────────────────
        if days_available <= TIER1_MAX:
            tier = 1
        elif days_available <= TIER2_MAX:
            tier = 2
        elif days_available <= TIER3_MAX:
            tier = 3
        else:
            tier = 4

        # ── Tier metadata ─────────────────────────────────────────────────────
        tier_defaults = {
            1: dict(
                max_days=3,
                confidence="VERY_LOW",
                message=(
                    "Early estimate based on limited data. "
                    "Accuracy improves as more logs are added."
                ),
            ),
            2: dict(
                max_days=7,
                confidence="LOW",
                message="Trend-based estimate. Full AI forecasting unlocks at 14 days.",
            ),
            3: dict(
                max_days=14,
                confidence="MEDIUM",
                message="Prophet-based forecast. Full accuracy unlocks at 30 days.",
            ),
            4: dict(
                max_days=30,
                confidence="HIGH",
                message=None,
            ),
        }

        meta       = tier_defaults[tier]
        cap        = meta["max_days"]
        horizon    = min(forecast_days, cap) if forecast_days is not None else cap
        confidence = meta["confidence"]
        message    = meta["message"]

        logger.info(
            "[MilkProductionForecaster] tier=%d days_available=%d horizon=%d",
            tier, days_available, horizon,
        )

        # ── Fetch history for training ────────────────────────────────────────
        # For Tiers 1-2 use ALL data (ignore days_history window — too little data).
        effective_history = days_history if tier >= 3 else max(days_available + 1, 30)
        history_df = self._fetch_history(cattle_id, effective_history)

        # ── Dispatch to tier-specific model ───────────────────────────────────
        if tier == 1:
            result_df = self._tier1_flat_average(history_df, horizon)
        elif tier == 2:
            result_df = self._tier2_linear_regression(history_df, horizon)
        elif tier == 3:
            result_df = self._tier3_prophet_weekly(history_df, horizon)
        else:
            result_df = self._tier4_prophet_full(history_df, horizon)

        result_df["yhat_lower"] = result_df["yhat_lower"].clip(lower=0.0)
        result_df["yhat"]       = result_df["yhat"].clip(lower=0.0)

        logger.info(
            "[MilkProductionForecaster] done: %d rows tier=%d confidence=%s",
            len(result_df), tier, confidence,
        )

        return ForecastResult(
            df=result_df,
            tier=tier,
            confidence=confidence,
            message=message,
            days_of_data_available=days_available,
        )

    # ── Tier implementations ──────────────────────────────────────────────────

    @staticmethod
    def _tier1_flat_average(history_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Tier 1: flat projection at the mean of all available daily totals."""
        avg   = float(history_df["y"].mean())
        today = pd.Timestamp(date.today())
        dates = [today + pd.Timedelta(days=i + 1) for i in range(horizon)]

        # Simple ±10 % bounds for visual context
        margin = avg * 0.10
        return pd.DataFrame({
            "ds":          dates,
            "yhat":        [avg]            * horizon,
            "yhat_lower":  [avg - margin]   * horizon,
            "yhat_upper":  [avg + margin]   * horizon,
        })

    @staticmethod
    def _tier2_linear_regression(history_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Tier 2: scikit-learn LinearRegression trend extrapolation."""
        from sklearn.linear_model import LinearRegression
        import numpy as np

        X = np.arange(len(history_df)).reshape(-1, 1)
        y = history_df["y"].values

        model = LinearRegression()
        model.fit(X, y)

        future_X = np.arange(len(history_df), len(history_df) + horizon).reshape(-1, 1)
        preds    = model.predict(future_X)

        # Residual std as a simple confidence interval proxy
        residuals = y - model.predict(X)
        sigma     = float(np.std(residuals)) if len(residuals) > 1 else 0.0

        today = pd.Timestamp(date.today())
        dates = [today + pd.Timedelta(days=i + 1) for i in range(horizon)]

        return pd.DataFrame({
            "ds":         dates,
            "yhat":       preds.tolist(),
            "yhat_lower": (preds - 1.28 * sigma).tolist(),   # ~80 % CI lower
            "yhat_upper": (preds + 1.28 * sigma).tolist(),   # ~80 % CI upper
        })

    @staticmethod
    def _tier3_prophet_weekly(history_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Tier 3: Prophet with weekly seasonality only (no yearly)."""
        return MilkProductionForecaster._run_prophet(
            history_df, horizon,
            weekly_seasonality=True,
            yearly_seasonality=False,
        )

    @staticmethod
    def _tier4_prophet_full(history_df: pd.DataFrame, horizon: int) -> pd.DataFrame:
        """Tier 4: Prophet with both weekly and yearly seasonality."""
        return MilkProductionForecaster._run_prophet(
            history_df, horizon,
            weekly_seasonality=True,
            yearly_seasonality=True,
        )

    @staticmethod
    def _run_prophet(
        history_df: pd.DataFrame,
        horizon: int,
        weekly_seasonality: bool,
        yearly_seasonality: bool,
    ) -> pd.DataFrame:
        """Shared Prophet runner used by Tiers 3 and 4."""
        from prophet import Prophet

        import logging as _log
        _log.getLogger("prophet").setLevel(_log.WARNING)
        _log.getLogger("cmdstanpy").setLevel(_log.WARNING)

        model = Prophet(
            daily_seasonality=False,
            weekly_seasonality=weekly_seasonality,
            yearly_seasonality=yearly_seasonality,
            interval_width=0.80,
            uncertainty_samples=200,
        )
        model.fit(history_df)

        future = model.make_future_dataframe(periods=horizon, freq="D")
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            forecast = model.predict(future)

        today  = pd.Timestamp(date.today())
        result = (
            forecast[forecast["ds"] > today][["ds", "yhat", "yhat_lower", "yhat_upper"]]
            .head(horizon)
            .reset_index(drop=True)
        )
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    @staticmethod
    def _count_available_days(cattle_id: int) -> int:
        """Return the number of distinct MilkLog dates for this cattle."""
        from apps.milk.models import MilkLog
        return (
            MilkLog.objects
            .filter(cattle_id=cattle_id)
            .values("date")
            .distinct()
            .count()
        )

    @staticmethod
    def _fetch_history(cattle_id: int, days_history: int) -> pd.DataFrame:
        """Query MilkLog and return Prophet-compatible (ds, y) DataFrame."""
        from apps.milk.models import MilkLog

        cutoff = date.today() - timedelta(days=days_history)
        logs   = (
            MilkLog.objects
            .filter(cattle_id=cattle_id, date__gte=cutoff)
            .order_by("date")
            .values_list("date", "total_litres")
        )

        if not logs:
            return pd.DataFrame(columns=["ds", "y"])

        df        = pd.DataFrame(list(logs), columns=["ds", "y"])
        df["ds"]  = pd.to_datetime(df["ds"])
        df["y"]   = df["y"].astype(float)

        # Fill date gaps with rolling mean so Prophet sees a contiguous series
        date_range = pd.date_range(df["ds"].min(), df["ds"].max(), freq="D")
        df         = df.set_index("ds").reindex(date_range).rename_axis("ds").reset_index()
        df["y"]    = (
            df["y"]
            .fillna(df["y"].rolling(7, min_periods=1, center=True).mean())
            .ffill().bfill()
            .clip(lower=0.0)
        )
        return df
