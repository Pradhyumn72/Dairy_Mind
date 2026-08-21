"""
Production Forecast Celery tasks.

regenerate_forecasts
    Schedule : every Monday at 06:00 UTC
    What     : For every active cattle with ≥ 30 MilkLog records, run
               MilkProductionForecaster.fit_and_forecast() and persist the
               results to ProductionForecast, replacing any existing future rows.

generate_single_forecast
    Triggered : manually via POST /api/forecast/refresh/ (with cattle_id arg)
    What      : Same as above but for a single cattle.

generate_all_forecasts
    Schedule  : legacy nightly slot kept for backward compatibility with Beat.
    What      : Alias for regenerate_forecasts.
"""
import logging
from datetime import date

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)

# Minimum history days required — mirrors the forecaster constant
MIN_HISTORY_DAYS = 30


# ── regenerate_forecasts (Monday 06:00 UTC) ───────────────────────────────────

@shared_task(
    bind=True,
    name="forecast.tasks.regenerate_forecasts",
    max_retries=3,
    default_retry_delay=120,
    queue="forecast",
    soft_time_limit=20 * 60,   # 20 min soft limit (Prophet is slow for large herds)
    time_limit=25 * 60,
)
def regenerate_forecasts(self):
    """
    Regenerate 30-day milk production forecasts for all active cattle.

    Algorithm
    ---------
    1. Fetch all active Cattle.
    2. For each cattle, count available MilkLog records.
    3. Skip cattle with fewer than MIN_HISTORY_DAYS records (logs a warning).
    4. Fit Prophet on the last 90 days of history and forecast 30 days forward.
    5. Atomically delete existing future forecast rows and bulk-insert new ones.
    6. Accumulate per-cattle success/skip/error counts and return a summary dict.

    Returns
    -------
    dict
        {
            "total_cattle"    : int,
            "forecasted"      : int,   # new forecasts saved
            "skipped"         : int,   # insufficient data
            "errors"          : int,   # per-cattle exceptions caught
            "run_date"        : "YYYY-MM-DD"
        }
    """
    from apps.cattle.models import Cattle
    from apps.forecast.ml.production_forecaster import (
        InsufficientDataError,
        MilkProductionForecaster,
    )
    from apps.forecast.models import ProductionForecast
    from apps.milk.models import MilkLog
    from decimal import Decimal, ROUND_HALF_UP

    def _dec(v: float) -> Decimal:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    today = date.today()
    active_cattle = list(Cattle.objects.filter(is_active=True))
    forecaster    = MilkProductionForecaster()

    logger.info(
        "[regenerate_forecasts] Starting forecast run for %d active cattle",
        len(active_cattle),
    )

    stats = {
        "total_cattle": len(active_cattle),
        "forecasted":   0,
        "skipped":      0,
        "errors":       0,
        "run_date":     str(today),
    }

    for cattle in active_cattle:
        try:
            # Quick count guard — avoids expensive Prophet fit for sparse cattle
            log_count = MilkLog.objects.filter(cattle=cattle).count()
            if log_count < MIN_HISTORY_DAYS:
                logger.warning(
                    "[regenerate_forecasts] Skipping cattle=%s: only %d logs (need %d)",
                    cattle.tag_number, log_count, MIN_HISTORY_DAYS,
                )
                stats["skipped"] += 1
                continue

            forecast_df = forecaster.fit_and_forecast(
                cattle_id=cattle.pk,
                days_history=90,
                forecast_days=30,
            )

            with transaction.atomic():
                # Replace all future rows for this cattle
                ProductionForecast.objects.filter(
                    cattle=cattle,
                    forecast_date__gt=today,
                ).delete()

                ProductionForecast.objects.bulk_create([
                    ProductionForecast(
                        cattle=cattle,
                        forecast_date=row["ds"].date(),
                        predicted_litres=_dec(row["yhat"]),
                        confidence_lower=_dec(row["yhat_lower"]),
                        confidence_upper=_dec(row["yhat_upper"]),
                    )
                    for _, row in forecast_df.iterrows()
                ])

            stats["forecasted"] += 1
            logger.info(
                "[regenerate_forecasts] Forecasted cattle=%s (%d rows)",
                cattle.tag_number, len(forecast_df),
            )

        except InsufficientDataError as exc:
            # Raised when MilkLog count passes the guard but forecaster still
            # doesn't have enough after filtering to the history window
            logger.warning(
                "[regenerate_forecasts] Insufficient data for cattle=%s: %s",
                cattle.tag_number, exc,
            )
            stats["skipped"] += 1

        except Exception as exc:
            # Per-cattle error — log but continue to next cattle
            stats["errors"] += 1
            logger.error(
                "[regenerate_forecasts] Error for cattle=%s: %s",
                cattle.tag_number, exc, exc_info=True,
            )

    logger.info(
        "[regenerate_forecasts] Done. forecasted=%d skipped=%d errors=%d",
        stats["forecasted"], stats["skipped"], stats["errors"],
    )

    # If more than half the herd errored, surface it via retry
    if stats["errors"] > stats["total_cattle"] // 2 and stats["total_cattle"] > 0:
        raise self.retry(
            exc=RuntimeError(
                f"More than half the herd ({stats['errors']}/{stats['total_cattle']}) "
                "encountered forecast errors."
            ),
            countdown=120 * (2 ** self.request.retries),
        )

    return stats


# ── generate_single_forecast ──────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="forecast.tasks.generate_single_forecast",
    max_retries=3,
    default_retry_delay=60,
    queue="forecast",
    soft_time_limit=5 * 60,
    time_limit=8 * 60,
)
def generate_single_forecast(self, cattle_id: int, forecast_days: int = 30):
    """
    Generate a forecast for a single cattle and persist results.

    Parameters
    ----------
    cattle_id     : int — Cattle PK
    forecast_days : int — number of days to forecast (default 30)

    Returns
    -------
    dict  { "cattle_id": int, "rows_saved": int }
    """
    from apps.cattle.models import Cattle
    from apps.forecast.ml.production_forecaster import (
        InsufficientDataError,
        MilkProductionForecaster,
    )
    from apps.forecast.models import ProductionForecast
    from decimal import Decimal, ROUND_HALF_UP

    def _dec(v: float) -> Decimal:
        return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    try:
        cattle = Cattle.objects.get(pk=cattle_id)
    except Cattle.DoesNotExist:
        logger.error("[generate_single_forecast] Cattle id=%d not found", cattle_id)
        return {"cattle_id": cattle_id, "rows_saved": 0, "error": "Cattle not found"}

    try:
        forecaster  = MilkProductionForecaster()
        forecast_df = forecaster.fit_and_forecast(
            cattle_id=cattle_id,
            days_history=90,
            forecast_days=forecast_days,
        )

        today = date.today()
        with transaction.atomic():
            ProductionForecast.objects.filter(
                cattle=cattle, forecast_date__gt=today
            ).delete()

            ProductionForecast.objects.bulk_create([
                ProductionForecast(
                    cattle=cattle,
                    forecast_date=row["ds"].date(),
                    predicted_litres=_dec(row["yhat"]),
                    confidence_lower=_dec(row["yhat_lower"]),
                    confidence_upper=_dec(row["yhat_upper"]),
                )
                for _, row in forecast_df.iterrows()
            ])

        logger.info(
            "[generate_single_forecast] Saved %d rows for cattle_id=%d",
            len(forecast_df), cattle_id,
        )
        return {"cattle_id": cattle_id, "rows_saved": len(forecast_df)}

    except InsufficientDataError as exc:
        logger.warning(
            "[generate_single_forecast] %s", exc
        )
        return {"cattle_id": cattle_id, "rows_saved": 0, "error": str(exc)}

    except Exception as exc:
        logger.error(
            "[generate_single_forecast] Failed for cattle_id=%d: %s",
            cattle_id, exc, exc_info=True,
        )
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# ── generate_all_forecasts (backward-compat alias) ───────────────────────────

@shared_task(
    bind=True,
    name="forecast.tasks.generate_all_forecasts",
    max_retries=3,
    default_retry_delay=120,
    queue="forecast",
)
def generate_all_forecasts(self):
    """
    Backward-compatible alias for regenerate_forecasts.
    Kept so existing Beat entries pointing at this task name continue to work.
    """
    logger.info(
        "[generate_all_forecasts] Delegating to regenerate_forecasts"
    )
    return regenerate_forecasts.apply_async().get(timeout=25 * 60)
