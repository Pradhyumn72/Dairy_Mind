"""
Production Forecast API views.

CattleForecastView      GET  /api/forecast/{cattle_id}/?days=30
    Runs (or retrieves cached) forecast for a single cattle (by PK).
    Returns Chart.js-compatible JSON with tier/confidence metadata.

ForecastByTagView       GET  /api/forecast/by-tag/{tag_number}/?days=30
    Same as CattleForecastView but looks up the cattle by tag_number string.
    Returns 404 if the tag doesn't match any active cattle.

ForecastRefreshView     POST /api/forecast/refresh/
    Synchronously regenerates forecasts for all active cattle.

HerdForecastView        GET  /api/forecast/herd/
    Aggregates the most recent per-cattle forecasts into a herd-level view.
"""
import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.shortcuts import get_object_or_404

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import IsOwnerOrReadOnly, IsVetOrOwner
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cattle.models import Cattle
from .ml.production_forecaster import InsufficientDataError, MilkProductionForecaster
from .models import ProductionForecast

logger = logging.getLogger(__name__)

# Maximum age of a cached forecast before re-generation is triggered on GET
CACHE_STALENESS_HOURS = 24


def _to_decimal(value: float) -> Decimal:
    """Round a float to 2 decimal places and return a Decimal."""
    return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ── Cattle forecast ───────────────────────────────────────────────────────────

class CattleForecastView(APIView):
    """
    Return a milk production forecast for a single cattle.

    GET /api/forecast/{cattle_id}/?days=30

    Path param
    ----------
    cattle_id : int — Cattle PK

    Query params
    ------------
    days     : int 1–90 (default 30)
        Requested forecast horizon — capped by the tier's maximum.
    history  : int (default 90)
        Days of historical MilkLog data to train on.
    refresh  : "true" (default "false")
        Force re-generation even if a fresh cached forecast exists.

    Response 200 — Chart.js-ready payload
    --------------------------------------
    {
        "cattle_id"             : int,
        "tag_number"            : str,
        "generated_at"          : "ISO-8601 datetime",
        "forecast_days"         : int,
        "stale"                 : bool,
        "tier"                  : 1 | 2 | 3 | 4,
        "confidence"            : "VERY_LOW" | "LOW" | "MEDIUM" | "HIGH",
        "message"               : str | null,
        "days_of_data_available": int,
        "labels"                : ["YYYY-MM-DD", ...],
        "predicted"             : [float, ...],
        "lower_bound"           : [float, ...],
        "upper_bound"           : [float, ...]
    }

    Response 400 — cattle has zero milk log data.
    Response 404 — Cattle not found.
    """

    permission_classes = [IsOwnerOrReadOnly]

    @extend_schema(summary="Get Details")
    def get(self, request, cattle_id: int):
        cattle = get_object_or_404(Cattle, pk=cattle_id)

        # ── Parse query params ────────────────────────────────────────────────
        try:
            forecast_days = int(request.query_params.get("days", 30))
            history_days  = int(request.query_params.get("history", 90))
        except (TypeError, ValueError):
            return Response(
                {"detail": "Query params 'days' and 'history' must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not (1 <= forecast_days <= 90):
            return Response(
                {"detail": "'days' must be between 1 and 90."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        force_refresh = request.query_params.get("refresh", "false").lower() == "true"

        # ── Check cache ───────────────────────────────────────────────────────
        from django.utils import timezone
        staleness_cutoff = timezone.now() - timedelta(hours=CACHE_STALENESS_HOURS)

        existing_qs = (
            ProductionForecast.objects
            .filter(cattle=cattle, forecast_date__gt=date.today())
            .order_by("forecast_date")
        )

        is_stale = False
        if existing_qs.exists() and not force_refresh:
            most_recent_generated = (
                existing_qs
                .order_by("-generated_at")
                .values_list("generated_at", flat=True)
                .first()
            )
            if most_recent_generated and most_recent_generated >= staleness_cutoff:
                logger.info(
                    "[CattleForecastView] Serving cached forecast for cattle_id=%d",
                    cattle_id,
                )
                # For cached responses we can't recover tier/confidence from DB rows,
                # so we recompute metadata cheaply (no model fit).
                meta = _cheap_tier_meta(cattle_id)
                return self._build_response(
                    cattle, existing_qs[:forecast_days], is_stale=False, meta=meta
                )
            else:
                is_stale = True
                logger.info(
                    "[CattleForecastView] Cached forecast for cattle_id=%d is stale, regenerating",
                    cattle_id,
                )

        # ── Generate fresh forecast ───────────────────────────────────────────
        try:
            forecaster  = MilkProductionForecaster()
            result      = forecaster.fit_and_forecast(
                cattle_id=cattle_id,
                days_history=history_days,
                forecast_days=forecast_days,
            )
        except InsufficientDataError as exc:
            return Response(
                {
                    "detail":                str(exc),
                    "available_days":        exc.available,
                    "required_days":         exc.required,
                    "days_of_data_available": 0,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        forecast_df = result.df

        # ── Persist to DB (delete old future rows first) ──────────────────────
        with transaction.atomic():
            ProductionForecast.objects.filter(
                cattle=cattle,
                forecast_date__gt=date.today(),
            ).delete()

            new_rows = [
                ProductionForecast(
                    cattle=cattle,
                    forecast_date=row["ds"].date(),
                    predicted_litres=_to_decimal(row["yhat"]),
                    confidence_lower=_to_decimal(row["yhat_lower"]),
                    confidence_upper=_to_decimal(row["yhat_upper"]),
                )
                for _, row in forecast_df.iterrows()
            ]
            ProductionForecast.objects.bulk_create(new_rows)

        logger.info(
            "[CattleForecastView] Saved %d forecast rows for cattle_id=%d (tier=%d)",
            len(new_rows), cattle_id, result.tier,
        )

        saved_qs = (
            ProductionForecast.objects
            .filter(cattle=cattle, forecast_date__gt=date.today())
            .order_by("forecast_date")
        )

        meta = {
            "tier":                   result.tier,
            "confidence":             result.confidence,
            "message":                result.message,
            "days_of_data_available": result.days_of_data_available,
        }
        return self._build_response(
            cattle, saved_qs[:forecast_days], is_stale=is_stale, meta=meta
        )

    @staticmethod
    def _build_response(cattle, qs, is_stale: bool, meta: dict) -> Response:
        """Serialise a queryset of ProductionForecast rows into Chart.js JSON."""
        rows = list(qs)
        if not rows:
            return Response(
                {"detail": "No forecast data available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        generated_at = rows[0].generated_at.isoformat() if rows else None

        return Response(
            {
                "cattle_id":              cattle.pk,
                "tag_number":             cattle.tag_number,
                "generated_at":           generated_at,
                "forecast_days":          len(rows),
                "stale":                  is_stale,
                # ── Progressive forecast metadata ──────────────────────────
                "tier":                   meta.get("tier"),
                "confidence":             meta.get("confidence"),
                "message":                meta.get("message"),
                "days_of_data_available": meta.get("days_of_data_available"),
                # ── Chart data ─────────────────────────────────────────────
                "labels":                 [str(r.forecast_date) for r in rows],
                "predicted":              [float(r.predicted_litres) for r in rows],
                "lower_bound":            [float(r.confidence_lower) for r in rows],
                "upper_bound":            [float(r.confidence_upper) for r in rows],
            },
            status=status.HTTP_200_OK,
        )


# ── Helper: cheap tier metadata without model fit ─────────────────────────────

def _cheap_tier_meta(cattle_id: int) -> dict:
    """
    Return tier/confidence/message/days_of_data_available by counting MilkLog
    records — no model fitting required.  Used when serving from cache.
    """
    from apps.forecast.ml.production_forecaster import (
        TIER1_MAX, TIER2_MAX, TIER3_MAX,
    )

    from apps.milk.models import MilkLog
    days = (
        MilkLog.objects
        .filter(cattle_id=cattle_id)
        .values("date")
        .distinct()
        .count()
    )

    if days == 0:
        return {"tier": None, "confidence": None, "message": None, "days_of_data_available": 0}
    elif days <= TIER1_MAX:
        tier, conf, msg = 1, "VERY_LOW", (
            "Early estimate based on limited data. "
            "Accuracy improves as more logs are added."
        )
    elif days <= TIER2_MAX:
        tier, conf, msg = 2, "LOW", "Trend-based estimate. Full AI forecasting unlocks at 14 days."
    elif days <= TIER3_MAX:
        tier, conf, msg = 3, "MEDIUM", "Prophet-based forecast. Full accuracy unlocks at 30 days."
    else:
        tier, conf, msg = 4, "HIGH", None

    return {
        "tier":                   tier,
        "confidence":             conf,
        "message":                msg,
        "days_of_data_available": days,
    }


# ── Forecast by tag number ────────────────────────────────────────────────────

class ForecastByTagView(APIView):
    """
    Return a milk production forecast for a cattle looked up by tag_number.

    GET /api/forecast/by-tag/{tag_number}/?days=30

    Path param
    ----------
    tag_number : str — the cattle's tag number (exact match, active cattle only)

    Query params
    ------------
    days    : int 1–90 (default 30) — capped by tier maximum
    history : int (default 90)
    refresh : "true" | "false" (default "false")

    Response 200 — identical schema to CattleForecastView
    Response 400 — zero milk log data for this cattle
    Response 404 — no active cattle with this tag_number
    """

    permission_classes = [IsOwnerOrReadOnly]

    @extend_schema(summary="Get Details")
    def get(self, request, tag_number: str):
        try:
            cattle = Cattle.objects.get(tag_number=tag_number, is_active=True)
        except Cattle.DoesNotExist:
            return Response(
                {
                    "detail": (
                        f"No active cattle found with tag number '{tag_number}'. "
                        "Check the tag number and try again."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # Delegate to CattleForecastView with the resolved PK — reuses all
        # caching, tier, and persistence logic without duplication.
        return CattleForecastView.as_view()(
            request._request,
            cattle_id=cattle.pk,
        )


# ── Forecast refresh ──────────────────────────────────────────────────────────

class ForecastRefreshView(APIView):
    """
    Regenerate forecasts for all active cattle using the progressive tier system.

    POST /api/forecast/refresh/

    Runs synchronously inline (no Celery worker required) so that
    ProductionForecast records are created immediately.  Any cattle with
    ≥ 1 day of milk log data will receive a forecast.

    Response 200
    ------------
    {
        "detail"       : "Forecasts regenerated.",
        "total_cattle" : int,
        "forecasted"   : int,
        "skipped"      : int,
        "errors"       : int
    }
    """

    permission_classes = [IsOwnerOrReadOnly]

    @extend_schema(summary="Submit Data")
    def post(self, request):
        from apps.cattle.models import Cattle
        from apps.milk.models import MilkLog
        from .ml.production_forecaster import InsufficientDataError, MilkProductionForecaster

        today         = date.today()
        active_cattle = list(Cattle.objects.filter(is_active=True))
        forecaster    = MilkProductionForecaster()

        stats = {"total_cattle": len(active_cattle), "forecasted": 0,
                 "skipped": 0, "errors": 0}

        for cattle in active_cattle:
            try:
                if MilkLog.objects.filter(cattle=cattle).count() == 0:
                    stats["skipped"] += 1
                    continue

                result = forecaster.fit_and_forecast(
                    cattle_id=cattle.pk,
                    days_history=90,
                )

                with transaction.atomic():
                    ProductionForecast.objects.filter(
                        cattle=cattle, forecast_date__gt=today,
                    ).delete()
                    ProductionForecast.objects.bulk_create([
                        ProductionForecast(
                            cattle=cattle,
                            forecast_date=row["ds"].date(),
                            predicted_litres=_to_decimal(row["yhat"]),
                            confidence_lower=_to_decimal(row["yhat_lower"]),
                            confidence_upper=_to_decimal(row["yhat_upper"]),
                        )
                        for _, row in result.df.iterrows()
                    ])

                stats["forecasted"] += 1
                logger.info(
                    "[ForecastRefreshView] cattle=%s tier=%d confidence=%s",
                    cattle.tag_number, result.tier, result.confidence,
                )

            except InsufficientDataError:
                stats["skipped"] += 1
            except Exception as exc:
                stats["errors"] += 1
                logger.error(
                    "[ForecastRefreshView] Error for cattle=%s: %s",
                    cattle.tag_number, exc, exc_info=True,
                )

        logger.info(
            "[ForecastRefreshView] Done by user=%s — %s",
            request.user, stats,
        )
        return Response(
            {
                "detail":        "Forecasts regenerated.",
                "total_cattle":  stats["total_cattle"],
                "forecasted":    stats["forecasted"],
                "skipped":       stats["skipped"],
                "errors":        stats["errors"],
            },
            status=status.HTTP_200_OK,
        )


# ── Herd forecast ─────────────────────────────────────────────────────────────

class HerdForecastView(APIView):
    """
    Return a herd-level forecast by summing the most recent per-cattle
    forecasts for all active cattle.

    GET /api/forecast/herd/?days=30

    Query params
    ------------
    days : int 1–90 (default 30)

    Response 200
    ------------
    {
        "forecast_days"      : int,
        "cattle_included"    : int,
        "labels"             : ["YYYY-MM-DD", ...],
        "predicted"          : [float, ...],
        "lower_bound"        : [float, ...],
        "upper_bound"        : [float, ...]
    }

    Response 404 — no forecast data available for any cattle.
    """

    permission_classes = [IsOwnerOrReadOnly]

    @extend_schema(summary="Get Details")
    def get(self, request):
        try:
            forecast_days = int(request.query_params.get("days", 30))
        except (TypeError, ValueError):
            return Response(
                {"detail": "'days' must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not (1 <= forecast_days <= 90):
            return Response(
                {"detail": "'days' must be between 1 and 90."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        today = date.today()

        forecast_dates = list(
            ProductionForecast.objects
            .filter(cattle__is_active=True, forecast_date__gt=today)
            .values_list("forecast_date", flat=True)
            .distinct()
            .order_by("forecast_date")[:forecast_days]
        )

        if not forecast_dates:
            return Response(
                {
                    "detail": (
                        "No herd forecast data available. "
                        "Run POST /api/forecast/refresh/ to generate forecasts."
                    )
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        from django.db.models import Sum
        labels, predicted, lower_bound, upper_bound = [], [], [], []
        cattle_set: set[int] = set()

        for fdate in forecast_dates:
            rows = ProductionForecast.objects.filter(
                cattle__is_active=True,
                forecast_date=fdate,
            ).select_related("cattle")

            agg = rows.aggregate(
                total_pred=Sum("predicted_litres"),
                total_lower=Sum("confidence_lower"),
                total_upper=Sum("confidence_upper"),
            )
            cattle_set.update(rows.values_list("cattle_id", flat=True))

            labels.append(str(fdate))
            predicted.append(round(float(agg["total_pred"] or 0), 2))
            lower_bound.append(round(float(agg["total_lower"] or 0), 2))
            upper_bound.append(round(float(agg["total_upper"] or 0), 2))

        return Response(
            {
                "forecast_days":   len(labels),
                "cattle_included": len(cattle_set),
                "labels":          labels,
                "predicted":       predicted,
                "lower_bound":     lower_bound,
                "upper_bound":     upper_bound,
            },
            status=status.HTTP_200_OK,
        )
