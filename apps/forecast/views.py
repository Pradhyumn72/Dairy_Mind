"""
Production Forecast API views.

CattleForecastView      GET  /api/forecast/{cattle_id}/?days=30
    Runs (or retrieves cached) forecast for a single cattle.
    Returns Chart.js-compatible JSON.

ForecastRefreshView     POST /api/forecast/refresh/
    Enqueues background regeneration of forecasts for all eligible cattle.

HerdForecastView        GET  /api/forecast/herd/
    Aggregates the most recent per-cattle forecasts into a herd-level view.
"""
import logging
from datetime import date, timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.shortcuts import get_object_or_404

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
    Return a 30-day milk production forecast for a single cattle.

    GET /api/forecast/{cattle_id}/?days=30

    Path param
    ----------
    cattle_id : int — Cattle PK

    Query params
    ------------
    days     : int 1–90 (default 30)
        Number of future days to forecast.
    history  : int (default 90)
        Days of historical MilkLog data to train on.
    refresh  : "true" (default "false")
        Force re-generation even if a fresh cached forecast exists.

    Response 200 — Chart.js-ready payload
    --------------------------------------
    {
        "cattle_id"    : int,
        "tag_number"   : str,
        "generated_at" : "ISO-8601 datetime",
        "forecast_days": int,
        "stale"        : bool,   // true if cached result is > 24 h old
        "labels"       : ["YYYY-MM-DD", ...],
        "predicted"    : [float, ...],
        "lower_bound"  : [float, ...],
        "upper_bound"  : [float, ...]
    }

    Response 400
    ------------
    { "detail": "...", "available_days": int, "required_days": int }
        Returned when the cattle has fewer than 30 days of MilkLog data.

    Response 404 — Cattle not found.
    """

    permission_classes = [IsOwnerOrReadOnly]

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
            .filter(
                cattle=cattle,
                forecast_date__gt=date.today(),
            )
            .order_by("forecast_date")
        )

        is_stale = False
        if existing_qs.exists() and not force_refresh:
            most_recent_generated = existing_qs.order_by("-generated_at").values_list(
                "generated_at", flat=True
            ).first()

            if most_recent_generated and most_recent_generated >= staleness_cutoff:
                # Serve from cache
                logger.info(
                    "[CattleForecastView] Serving cached forecast for cattle_id=%d",
                    cattle_id,
                )
                return self._build_response(
                    cattle, existing_qs[:forecast_days], is_stale=False
                )
            else:
                is_stale = True
                logger.info(
                    "[CattleForecastView] Cached forecast for cattle_id=%d is stale, regenerating",
                    cattle_id,
                )

        # ── Generate fresh forecast ───────────────────────────────────────────
        try:
            forecaster = MilkProductionForecaster()
            forecast_df = forecaster.fit_and_forecast(
                cattle_id=cattle_id,
                days_history=history_days,
                forecast_days=forecast_days,
            )
        except InsufficientDataError as exc:
            return Response(
                {
                    "detail": str(exc),
                    "available_days": exc.available,
                    "required_days":  exc.required,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

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
            "[CattleForecastView] Saved %d forecast rows for cattle_id=%d",
            len(new_rows), cattle_id,
        )

        saved_qs = (
            ProductionForecast.objects
            .filter(cattle=cattle, forecast_date__gt=date.today())
            .order_by("forecast_date")
        )
        return self._build_response(cattle, saved_qs[:forecast_days], is_stale=is_stale)

    @staticmethod
    def _build_response(cattle, qs, is_stale: bool) -> Response:
        """Serialise a queryset of ProductionForecast rows into Chart.js JSON."""
        rows = list(qs)
        if not rows:
            return Response(
                {"detail": "No forecast data available."},
                status=status.HTTP_404_NOT_FOUND,
            )

        from django.utils import timezone
        generated_at = rows[0].generated_at.isoformat() if rows else None

        return Response(
            {
                "cattle_id":     cattle.pk,
                "tag_number":    cattle.tag_number,
                "generated_at":  generated_at,
                "forecast_days": len(rows),
                "stale":         is_stale,
                "labels":        [str(r.forecast_date) for r in rows],
                "predicted":     [float(r.predicted_litres) for r in rows],
                "lower_bound":   [float(r.confidence_lower) for r in rows],
                "upper_bound":   [float(r.confidence_upper) for r in rows],
            },
            status=status.HTTP_200_OK,
        )


# ── Forecast refresh ──────────────────────────────────────────────────────────

class ForecastRefreshView(APIView):
    """
    Enqueue a background task to regenerate forecasts for all active cattle.

    POST /api/forecast/refresh/

    Response 202
    ------------
    {
        "detail"  : "Forecast regeneration task queued.",
        "task_id" : "<celery-task-id>"
    }
    """

    permission_classes = [IsOwnerOrReadOnly]

    def post(self, request):
        from .tasks import regenerate_forecasts
        result = regenerate_forecasts.apply_async()
        logger.info(
            "[ForecastRefreshView] Queued regenerate_forecasts task_id=%s by user=%s",
            result.id, request.user,
        )
        return Response(
            {
                "detail":  "Forecast regeneration task queued.",
                "task_id": result.id,
            },
            status=status.HTTP_202_ACCEPTED,
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

        # Get the next `forecast_days` distinct forecast dates that have data
        forecast_dates = list(
            ProductionForecast.objects
            .filter(
                cattle__is_active=True,
                forecast_date__gt=today,
            )
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
                "forecast_days":    len(labels),
                "cattle_included":  len(cattle_set),
                "labels":           labels,
                "predicted":        predicted,
                "lower_bound":      lower_bound,
                "upper_bound":      upper_bound,
            },
            status=status.HTTP_200_OK,
        )
