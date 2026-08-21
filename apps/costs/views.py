"""
Cost Optimizer API views.

FeedLogListCreateView   GET/POST  /api/costs/feed-log/
    List all feed logs (filterable) or create a new one.

CattleMonthlySummaryView  GET  /api/costs/summary/{cattle_id}/?month=MM&year=YYYY
    Run (or re-run) the ROI calculator for a single cattle in a month and
    return the full breakdown.

FarmWideSummaryView       GET  /api/costs/summary/farm/?month=MM&year=YYYY
    Run the farm-wide aggregation for all active cattle and return totals +
    top-5 / bottom-5 ranked by profit.

FeedLogDetailView         GET/PUT/PATCH/DELETE  /api/costs/feed-log/{id}/
    Single feed log operations.
"""
import logging
from datetime import date

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import IsOwnerOrReadOnly, IsVetOrOwner
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cattle.models import Cattle
from django.shortcuts import get_object_or_404

from .calculator import FeedYieldCalculator
from .models import FeedLog
from .serializers import CostSummarySerializer, FeedLogSerializer

logger = logging.getLogger(__name__)


# ── Feed log list / create ────────────────────────────────────────────────────

class FeedLogListCreateView(APIView):
    """
    List all feed logs or create a new one.

    GET  /api/costs/feed-log/
        Query params (all optional):
            cattle_id  int   — filter by cattle PK
            date_from  date  — YYYY-MM-DD
            date_to    date  — YYYY-MM-DD
            feed_type  str   — case-insensitive substring match

        Response 200:
        {
            "count"  : int,
            "results": [ ...FeedLogSerializer... ]
        }

    POST /api/costs/feed-log/
        Body (JSON or form):
            cattle_id   int     (required)
            date        date    (required, not future)
            feed_type   str     (required)
            quantity_kg decimal (required, > 0)
            cost_per_kg decimal (required, > 0)

        Response 201: created FeedLog with auto-computed total_cost.
        Response 400: validation error.
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        qs = FeedLog.objects.select_related("cattle").order_by("-date")

        cattle_id = request.query_params.get("cattle_id")
        date_from = request.query_params.get("date_from")
        date_to   = request.query_params.get("date_to")
        feed_type = request.query_params.get("feed_type")

        if cattle_id:
            try:
                qs = qs.filter(cattle_id=int(cattle_id))
            except (ValueError, TypeError):
                return Response(
                    {"detail": "cattle_id must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if date_from:
            try:
                qs = qs.filter(date__gte=date.fromisoformat(date_from))
            except ValueError:
                return Response(
                    {"detail": f"Invalid date_from '{date_from}'. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if date_to:
            try:
                qs = qs.filter(date__lte=date.fromisoformat(date_to))
            except ValueError:
                return Response(
                    {"detail": f"Invalid date_to '{date_to}'. Use YYYY-MM-DD."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        if feed_type:
            qs = qs.filter(feed_type__icontains=feed_type)

        serializer = FeedLogSerializer(qs, many=True)
        return Response(
            {"count": qs.count(), "results": serializer.data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        serializer = FeedLogSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        log = serializer.save()
        logger.info(
            "[FeedLogListCreateView] FeedLog created: cattle=%s date=%s "
            "feed=%s total=%.2f by=%s",
            log.cattle.tag_number, log.date,
            log.feed_type, log.total_cost, request.user,
        )
        return Response(
            FeedLogSerializer(log).data,
            status=status.HTTP_201_CREATED,
        )


# ── Feed log detail ───────────────────────────────────────────────────────────

class FeedLogDetailView(APIView):
    """
    Retrieve, update, or delete a single FeedLog.

    GET    /api/costs/feed-log/{id}/
    PUT    /api/costs/feed-log/{id}/
    PATCH  /api/costs/feed-log/{id}/
    DELETE /api/costs/feed-log/{id}/
    """

    permission_classes = [IsOwnerOrReadOnly]

    def _get_log(self, pk: int):
        return get_object_or_404(FeedLog.objects.select_related("cattle"), pk=pk)

    def get(self, request, pk: int):
        return Response(FeedLogSerializer(self._get_log(pk)).data)

    def put(self, request, pk: int):
        log = self._get_log(pk)
        serializer = FeedLogSerializer(log, data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)

    def patch(self, request, pk: int):
        log = self._get_log(pk)
        serializer = FeedLogSerializer(log, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, pk: int):
        log = self._get_log(pk)
        log.delete()
        logger.info("[FeedLogDetailView] FeedLog id=%d deleted by %s", pk, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ── Per-cattle monthly summary ────────────────────────────────────────────────

class CattleMonthlySummaryView(APIView):
    """
    Calculate and return the full ROI breakdown for a single cattle in a month.

    GET /api/costs/summary/{cattle_id}/?month=MM&year=YYYY

    Path param
    ----------
    cattle_id : int — Cattle PK

    Query params
    ------------
    month : int 1–12 (default: current month)
    year  : int      (default: current year)

    Response 200
    ------------
    {
        "cattle_id"           : int,
        "tag_number"          : str,
        "name"                : str,
        "month"               : int,
        "year"                : int,
        "total_feed_cost"     : float,   // INR
        "total_milk_litres"   : float,
        "milk_price_per_litre": float,   // INR
        "revenue"             : float,   // INR
        "profit"              : float,   // INR (negative = loss)
        "cost_per_litre"      : float | null,
        "profit_margin"       : float | null,
        "roi_ratio"           : float | null,
        "has_feed_data"       : bool,
        "has_milk_data"       : bool
    }

    Response 400 — invalid month/year.
    Response 404 — cattle not found.
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request, cattle_id: int):
        today = date.today()

        try:
            month = int(request.query_params.get("month", today.month))
            year  = int(request.query_params.get("year",  today.year))
        except (ValueError, TypeError):
            return Response(
                {"detail": "month and year must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not (1 <= month <= 12):
            return Response(
                {"detail": "month must be between 1 and 12."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        get_object_or_404(Cattle, pk=cattle_id)   # 404 guard

        try:
            calculator = FeedYieldCalculator()
            result = calculator.calculate_monthly_roi(
                cattle_id=cattle_id,
                month=month,
                year=year,
            )
        except Cattle.DoesNotExist:
            return Response(
                {"detail": f"Cattle with id={cattle_id} not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(result, status=status.HTTP_200_OK)


# ── Farm-wide monthly summary ─────────────────────────────────────────────────

class FarmWideSummaryView(APIView):
    """
    Aggregate ROI for all active cattle in a month and return farm totals
    plus ranked top-5 / bottom-5 by profit.

    GET /api/costs/summary/farm/?month=MM&year=YYYY

    Query params
    ------------
    month : int 1–12 (default: current month)
    year  : int      (default: current year)

    Response 200
    ------------
    {
        "month"                   : int,
        "year"                    : int,
        "milk_price_per_litre"    : float,
        "cattle_count"            : int,
        "farm_total_feed_cost"    : float,
        "farm_total_milk_litres"  : float,
        "farm_total_revenue"      : float,
        "farm_total_profit"       : float,
        "top_5_profitable"        : [ ...CattleROI... ],
        "bottom_5_profitable"     : [ ...CattleROI... ],
        "all_cattle"              : [ ...CattleROI... ]
    }
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        today = date.today()

        try:
            month = int(request.query_params.get("month", today.month))
            year  = int(request.query_params.get("year",  today.year))
        except (ValueError, TypeError):
            return Response(
                {"detail": "month and year must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not (1 <= month <= 12):
            return Response(
                {"detail": "month must be between 1 and 12."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        calculator = FeedYieldCalculator()
        summary    = calculator.farm_wide_summary(month=month, year=year)

        return Response(summary, status=status.HTTP_200_OK)


# ── Legacy stub views kept for backward URL compatibility ─────────────────────

class ROIView(APIView):
    """Deprecated — use CattleMonthlySummaryView or FarmWideSummaryView."""
    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        return Response(
            {"detail": "Use /api/costs/summary/{cattle_id}/ or /api/costs/summary/farm/ instead."},
            status=status.HTTP_301_MOVED_PERMANENTLY,
        )


class LowPerformersView(APIView):
    """Returns bottom-5 cattle from the farm-wide summary for the current month."""
    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        today = date.today()
        try:
            month = int(request.query_params.get("month", today.month))
            year  = int(request.query_params.get("year", today.year))
        except (ValueError, TypeError):
            return Response(
                {"detail": "month and year must be integers."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        calculator = FeedYieldCalculator()
        summary    = calculator.farm_wide_summary(month=month, year=year)
        return Response(
            {
                "month": month,
                "year":  year,
                "bottom_5_profitable": summary["bottom_5_profitable"],
            },
            status=status.HTTP_200_OK,
        )


class FarmConfigView(APIView):
    """Return or update the active milk price per litre setting."""
    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        from django.conf import settings as _s
        return Response(
            {"milk_price_per_litre": getattr(_s, "MILK_PRICE_PER_LITRE", 55.0)},
            status=status.HTTP_200_OK,
        )

    def put(self, request):
        # Runtime override via .env is the preferred mechanism.
        # This endpoint documents the current value; a proper admin interface
        # should use django-constance or a DB-backed config model.
        return Response(
            {
                "detail": (
                    "To change milk_price_per_litre, update MILK_PRICE_PER_LITRE "
                    "in your .env file and restart the server."
                )
            },
            status=status.HTTP_200_OK,
        )
