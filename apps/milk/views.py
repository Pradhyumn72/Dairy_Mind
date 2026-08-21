"""
Milk Tracker ViewSet and standalone API views.

MilkLogViewSet
--------------
Standard CRUD for MilkLog records with filtering and ordering.
Sets ``recorded_by`` automatically from the authenticated user on create.

Standalone views (registered separately in urls.py)
----------------------------------------------------
DailySummaryView    GET /api/milk/daily-summary/?date=YYYY-MM-DD
CattleTrendView     GET /api/milk/cattle/{id}/trend/?days=30
TopProducersView    GET /api/milk/top-producers/?month=MM&year=YYYY
"""
import logging
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Sum
from django.shortcuts import get_object_or_404

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import IsOwnerOrReadOnly, IsVetOrOwner
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cattle.models import Cattle

from .filters import MilkLogFilter
from .models import MilkLog
from .serializers import MilkLogSerializer, MilkStatsSerializer

logger = logging.getLogger(__name__)


# ── Helper ────────────────────────────────────────────────────────────────────

def _parse_positive_int(value: str | None, default: int, name: str, max_val: int = None):
    """
    Parse *value* as a positive integer, returning *default* if None/blank.
    Raises ValueError with a descriptive message on invalid input.
    """
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"'{name}' must be a valid integer.")
    if parsed <= 0:
        raise ValueError(f"'{name}' must be a positive integer.")
    if max_val is not None and parsed > max_val:
        raise ValueError(f"'{name}' must not exceed {max_val}.")
    return parsed


# ── Main CRUD ViewSet ─────────────────────────────────────────────────────────

class MilkLogViewSet(viewsets.ModelViewSet):
    """
    ViewSet for MilkLog CRUD operations.

    list     GET    /api/milk/logs/           Paginated, filterable list of milk logs.
    create   POST   /api/milk/logs/           Record a new milk log entry.
    retrieve GET    /api/milk/logs/{id}/      Single milk log detail.
    update   PUT    /api/milk/logs/{id}/      Full update.
    partial  PATCH  /api/milk/logs/{id}/      Partial update.
    destroy  DELETE /api/milk/logs/{id}/      Delete a log entry.

    Filters (via ?param=value)
    --------------------------
    cattle       int    — filter by cattle PK         (?cattle=3)
    date         date   — exact date match             (?date=2024-06-15)
    date_from    date   — date range start (inclusive) (?date_from=2024-06-01)
    date_to      date   — date range end   (inclusive) (?date_to=2024-06-30)

    Ordering (via ?ordering=field)
    ------------------------------
    date, -date, total_litres, -total_litres, cattle__tag_number

    Search (via ?search=term)
    -------------------------
    cattle__tag_number, cattle__name
    """

    queryset = (
        MilkLog.objects
        .select_related("cattle", "recorded_by")
        .order_by("-date")
    )
    serializer_class = MilkLogSerializer
    permission_classes = [IsOwnerOrReadOnly]

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = MilkLogFilter
    search_fields = ["cattle__tag_number", "cattle__name"]
    ordering_fields = ["date", "total_litres", "cattle__tag_number"]
    ordering = ["-date"]

    def perform_create(self, serializer):
        """
        Save a new MilkLog, setting ``recorded_by`` to the current user.

        The model's ``save()`` method auto-computes ``total_litres`` from
        morning + evening values before the DB write.
        """
        log = serializer.save(recorded_by=self.request.user)
        logger.info(
            "MilkLog created: cattle=%s date=%s total=%.2f by=%s",
            log.cattle.tag_number, log.date, log.total_litres, self.request.user,
        )

    def perform_update(self, serializer):
        """
        Update an existing MilkLog. ``recorded_by`` is not changed on updates —
        it reflects who originally entered the record.
        """
        log = serializer.save()
        logger.info(
            "MilkLog updated: id=%s cattle=%s date=%s by=%s",
            log.pk, log.cattle.tag_number, log.date, self.request.user,
        )


# ── Standalone views ──────────────────────────────────────────────────────────

class DailySummaryView(APIView):
    """
    Return total farm milk production for a single calendar day.

    GET /api/milk/daily-summary/?date=YYYY-MM-DD

    Query params
    ------------
    date : YYYY-MM-DD (required)
        The calendar date to summarise.  Must not be in the future.

    Response 200
    ------------
    {
        "date"           : "YYYY-MM-DD",
        "total_litres"   : float,   // herd total
        "cattle_count"   : int,     // number of cattle with a log that day
        "avg_per_cattle" : float    // total / cattle_count, or 0 if no logs
    }

    Response 400
    ------------
    { "detail": "<error message>" }
        Returned when the date param is missing, malformed, or in the future.
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        raw_date = request.query_params.get("date")
        if not raw_date:
            return Response(
                {"detail": "Query param 'date' is required (YYYY-MM-DD)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            query_date = date.fromisoformat(raw_date)
        except ValueError:
            return Response(
                {"detail": f"Invalid date format '{raw_date}'. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if query_date > date.today():
            return Response(
                {"detail": "date cannot be in the future."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        agg = MilkLog.objects.filter(date=query_date).aggregate(
            total=Sum("total_litres"),
            count=Count("id"),
        )
        total = float(agg["total"] or 0)
        count = agg["count"] or 0
        avg = round(total / count, 2) if count > 0 else 0.0

        return Response(
            {
                "date": str(query_date),
                "total_litres": round(total, 2),
                "cattle_count": count,
                "avg_per_cattle": avg,
            },
            status=status.HTTP_200_OK,
        )


class CattleTrendView(APIView):
    """
    Return daily milk totals for a single cattle over a trailing window.

    Designed for Chart.js line chart consumption — the response includes
    separate ``labels`` (dates) and ``data`` (totals) arrays alongside a
    ``logs`` array of full daily objects.

    GET /api/milk/cattle/{id}/trend/?days=30

    Path param
    ----------
    id : int — Cattle PK

    Query params
    ------------
    days : int  1–365, default 30
        Number of trailing calendar days to include (today - days + 1 → today).

    Response 200
    ------------
    {
        "cattle_id"   : int,
        "tag_number"  : str,
        "name"        : str,
        "period_days" : int,
        "period_start": "YYYY-MM-DD",
        "period_end"  : "YYYY-MM-DD",
        "chart": {
            "labels"  : ["YYYY-MM-DD", ...],   // one entry per day WITH a log
            "data"    : [float, ...]            // matching total_litres values
        },
        "summary": {
            "total_litres"   : float,
            "avg_daily"      : float,
            "max_daily"      : float,
            "log_days"       : int              // days that have a log entry
        },
        "logs": [
            {
                "date"           : "YYYY-MM-DD",
                "morning_litres" : float,
                "evening_litres" : float,
                "total_litres"   : float
            },
            ...
        ]
    }

    Response 400  — invalid ``days`` param
    Response 404  — Cattle not found
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request, cattle_id: int):
        cattle = get_object_or_404(Cattle, pk=cattle_id)

        try:
            days = _parse_positive_int(
                request.query_params.get("days"), default=30, name="days", max_val=365
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        period_end = date.today()
        period_start = period_end - timedelta(days=days - 1)

        logs_qs = (
            MilkLog.objects
            .filter(cattle=cattle, date__range=(period_start, period_end))
            .order_by("date")
            .values("date", "morning_litres", "evening_litres", "total_litres")
        )

        logs = list(logs_qs)

        # Aggregates
        totals = [float(log["total_litres"]) for log in logs]
        grand_total = round(sum(totals), 2)
        avg_daily = round(grand_total / len(totals), 2) if totals else 0.0
        max_daily = round(max(totals), 2) if totals else 0.0

        return Response(
            {
                "cattle_id": cattle.pk,
                "tag_number": cattle.tag_number,
                "name": cattle.name,
                "period_days": days,
                "period_start": str(period_start),
                "period_end": str(period_end),
                "chart": {
                    "labels": [str(log["date"]) for log in logs],
                    "data": totals,
                },
                "summary": {
                    "total_litres": grand_total,
                    "avg_daily": avg_daily,
                    "max_daily": max_daily,
                    "log_days": len(logs),
                },
                "logs": [
                    {
                        "date": str(log["date"]),
                        "morning_litres": float(log["morning_litres"]),
                        "evening_litres": float(log["evening_litres"]),
                        "total_litres": float(log["total_litres"]),
                    }
                    for log in logs
                ],
            },
            status=status.HTTP_200_OK,
        )


class TopProducersView(APIView):
    """
    Return a ranked list of cattle by total milk yield for a given month.

    GET /api/milk/top-producers/?month=MM&year=YYYY

    Query params
    ------------
    month : int 1–12  (default: current month)
    year  : int       (default: current year, max: current year)

    Response 200
    ------------
    {
        "month"    : int,
        "year"     : int,
        "count"    : int,          // number of cattle in the ranking
        "producers": [
            {
                "rank"            : int,   // 1-based, ascending by total
                "cattle_id"       : int,
                "tag_number"      : str,
                "name"            : str,
                "total_litres"    : float, // sum for the month
                "avg_daily_litres": float,
                "log_count"       : int    // number of days logged
            },
            ...
        ]
    }

    Response 400 — invalid month/year params
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        today = date.today()

        try:
            month = _parse_positive_int(
                request.query_params.get("month"),
                default=today.month,
                name="month",
                max_val=12,
            )
            year = _parse_positive_int(
                request.query_params.get("year"),
                default=today.year,
                name="year",
                max_val=today.year,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Aggregate per-cattle for the requested month/year
        rows = (
            MilkLog.objects
            .filter(date__year=year, date__month=month)
            .values("cattle__id", "cattle__tag_number", "cattle__name")
            .annotate(
                total_litres=Sum("total_litres"),
                avg_daily_litres=Avg("total_litres"),
                log_count=Count("id"),
            )
            .order_by("-total_litres")   # highest producer first
        )

        producers = [
            {
                "rank": idx + 1,
                "cattle_id": row["cattle__id"],
                "tag_number": row["cattle__tag_number"],
                "name": row["cattle__name"],
                "total_litres": round(float(row["total_litres"]), 2),
                "avg_daily_litres": round(float(row["avg_daily_litres"]), 2),
                "log_count": row["log_count"],
            }
            for idx, row in enumerate(rows)
        ]

        return Response(
            {
                "month": month,
                "year": year,
                "count": len(producers),
                "producers": producers,
            },
            status=status.HTTP_200_OK,
        )
