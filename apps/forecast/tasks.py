"""
Production Forecast Celery tasks.

regenerate_forecasts
    Schedule : every Monday at 06:00 UTC
    What     : For every active cattle with ≥ 1 MilkLog record, run
               MilkProductionForecaster.fit_and_forecast() using the
               progressive tier logic and persist the results.

generate_single_forecast
    Triggered : manually (with cattle_id arg)
    What      : Same as above but for a single cattle.

generate_all_forecasts
    Schedule  : legacy nightly slot kept for backward compatibility with Beat.
    What      : Alias for regenerate_forecasts.
"""
import logging
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from celery import shared_task
from django.db import transaction

logger = logging.getLogger(__name__)


def _dec(v: float) -> Decimal:
    return Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _persist_forecast(cattle, result, today: date) -> int:
    """
    Atomically replace future ProductionForecast rows for *cattle* with the
    rows in *result.df*.  Returns the number of rows saved.
    """
    from apps.forecast.models import ProductionForecast

    rows = [
        ProductionForecast(
            cattle=cattle,
            forecast_date=row["ds"].date(),
            predicted_litres=_dec(row["yhat"]),
            confidence_lower=_dec(row["yhat_lower"]),
            confidence_upper=_dec(row["yhat_upper"]),
        )
        for _, row in result.df.iterrows()
    ]

    with transaction.atomic():
        ProductionForecast.objects.filter(
            cattle=cattle,
            forecast_date__gt=today,
        ).delete()
        ProductionForecast.objects.bulk_create(rows)

    return len(rows)


# ── regenerate_forecasts ──────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="forecast.tasks.regenerate_forecasts",
    max_retries=3,
    default_retry_delay=120,
    queue="forecast",
    soft_time_limit=20 * 60,
    time_limit=25 * 60,
)
def regenerate_forecasts(self):
    """
    Regenerate milk production forecasts for ALL active cattle using the
    progressive tier system — any cattle with ≥ 1 day of milk logs gets
    a forecast (Tier 1–4 depending on history length).

    Returns
    -------
    dict  { total_cattle, forecasted, skipped (zero logs), errors, run_date }
    """
    from apps.cattle.models import Cattle
    from apps.forecast.ml.production_forecaster import (
        InsufficientDataError,
        MilkProductionForecaster,
    )
    from apps.milk.models import MilkLog

    today         = date.today()
    active_cattle = list(Cattle.objects.filter(is_active=True))
    forecaster    = MilkProductionForecaster()

    logger.info(
        "[regenerate_forecasts] Starting progressive forecast run for %d active cattle",
        len(active_cattle),
    )

    stats = {
        "total_cattle": len(active_cattle),
        "forecasted":   0,
        "skipped":      0,   # zero milk logs
        "errors":       0,
        "run_date":     str(today),
    }

    for cattle in active_cattle:
        try:
            # Fast count — skip only if truly zero logs
            log_count = MilkLog.objects.filter(cattle=cattle).count()
            if log_count == 0:
                logger.info(
                    "[regenerate_forecasts] Skipping cattle=%s — no milk logs yet",
                    cattle.tag_number,
                )
                stats["skipped"] += 1
                continue

            result = forecaster.fit_and_forecast(
                cattle_id=cattle.pk,
                days_history=90,
            )

            saved = _persist_forecast(cattle, result, today)

            stats["forecasted"] += 1
            logger.info(
                "[regenerate_forecasts] cattle=%s tier=%d confidence=%s rows=%d",
                cattle.tag_number, result.tier, result.confidence, saved,
            )

        except InsufficientDataError:
            # fit_and_forecast only raises this for zero logs; the count guard
            # above should prevent reaching here, but handle it defensively.
            stats["skipped"] += 1

        except Exception as exc:
            stats["errors"] += 1
            logger.error(
                "[regenerate_forecasts] Error for cattle=%s: %s",
                cattle.tag_number, exc, exc_info=True,
            )

    logger.info(
        "[regenerate_forecasts] Done. forecasted=%d skipped=%d errors=%d",
        stats["forecasted"], stats["skipped"], stats["errors"],
    )

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
def generate_single_forecast(self, cattle_id: int, forecast_days: int = None):
    """
    Generate a progressive-tier forecast for a single cattle and persist results.

    Parameters
    ----------
    cattle_id     : int — Cattle PK
    forecast_days : int | None — optional horizon override (capped by tier)

    Returns
    -------
    dict  { cattle_id, rows_saved, tier, confidence }
    """
    from apps.cattle.models import Cattle
    from apps.forecast.ml.production_forecaster import (
        InsufficientDataError,
        MilkProductionForecaster,
    )

    try:
        cattle = Cattle.objects.get(pk=cattle_id)
    except Cattle.DoesNotExist:
        logger.error("[generate_single_forecast] Cattle id=%d not found", cattle_id)
        return {"cattle_id": cattle_id, "rows_saved": 0, "error": "Cattle not found"}

    try:
        forecaster = MilkProductionForecaster()
        kwargs     = {"cattle_id": cattle_id, "days_history": 90}
        if forecast_days is not None:
            kwargs["forecast_days"] = forecast_days

        result = forecaster.fit_and_forecast(**kwargs)
        saved  = _persist_forecast(cattle, result, date.today())

        logger.info(
            "[generate_single_forecast] cattle_id=%d tier=%d confidence=%s rows=%d",
            cattle_id, result.tier, result.confidence, saved,
        )
        return {
            "cattle_id":  cattle_id,
            "rows_saved": saved,
            "tier":       result.tier,
            "confidence": result.confidence,
        }

    except InsufficientDataError as exc:
        logger.warning("[generate_single_forecast] %s", exc)
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
    logger.info("[generate_all_forecasts] Delegating to regenerate_forecasts")
    return regenerate_forecasts.apply_async().get(timeout=25 * 60)
