"""
Cattle Registry ViewSet.

Provides a complete REST API for managing Cattle records, including
full CRUD operations and four custom actions:

  GET  /api/cattle/{id}/milk-history/     → last 30 days of MilkLog entries
  GET  /api/cattle/{id}/health-timeline/  → combined HealthAlert + HealthRecord timeline
  GET  /api/cattle/{id}/dashboard/        → aggregated stats summary card
  POST /api/cattle/{id}/deactivate/       → soft-delete (sets is_active=False)

Filtering  : breed (icontains), gender (exact), is_active (bool)
Search     : name, tag_number  (case-insensitive partial match via ?search=)
Ordering   : name, date_of_birth, purchase_date  (via ?ordering=)
"""
import logging
from datetime import date, timedelta

from django.db.models import Avg, Max, Sum
from django.utils import timezone

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import IsOwnerOrReadOnly, IsVetOrOwner
from rest_framework.response import Response

from apps.health.models import HealthAlert, HealthRecord
from apps.milk.models import MilkLog

from .filters import CattleFilter
from .models import AnimalHistory, Cattle
from .serializers import (
    AnimalHistorySerializer,
    CattleListSerializer,
    CattleSerializer,
)

logger = logging.getLogger(__name__)


class CattleViewSet(viewsets.ModelViewSet):
    """
    ViewSet for the Cattle model.

    list     GET    /api/cattle/           Returns paginated, filterable list of cattle.
    create   POST   /api/cattle/           Create a new cattle record.
    retrieve GET    /api/cattle/{id}/      Return a single cattle record with full detail.
    update   PUT    /api/cattle/{id}/      Full update of a cattle record.
    partial  PATCH  /api/cattle/{id}/      Partial update of a cattle record.
    destroy  DELETE /api/cattle/{id}/      Hard delete (use /deactivate/ for soft-delete).

    Custom actions (see individual docstrings below)
    -----------------------------------------------
    milk_history    GET  /api/cattle/{id}/milk-history/
    health_timeline GET  /api/cattle/{id}/health-timeline/
    dashboard       GET  /api/cattle/{id}/dashboard/
    deactivate      POST /api/cattle/{id}/deactivate/
    history         GET  /api/cattle/{id}/history/
    """

    queryset = Cattle.objects.all().select_related()
    permission_classes = [IsOwnerOrReadOnly]

    # ── Filtering / search / ordering ─────────────────────────────────────────
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = CattleFilter
    search_fields = ["name", "tag_number"]          # ?search=daisy
    ordering_fields = ["name", "date_of_birth", "purchase_date"]
    ordering = ["tag_number"]                        # default sort

    # ── Serializer selection ──────────────────────────────────────────────────

    def get_serializer_class(self):
        """
        Return CattleListSerializer for list actions (lighter payload) and
        CattleSerializer for all other actions (full detail).
        """
        if self.action == "list":
            return CattleListSerializer
        return CattleSerializer

    # ── Audit-log helpers ─────────────────────────────────────────────────────

    def _record_history(self, cattle: Cattle, action_type: str, previous: dict, changed: list):
        """Write an AnimalHistory entry for auditing purposes."""
        AnimalHistory.objects.create(
            cattle=cattle,
            changed_by=self.request.user,
            action_type=action_type,
            previous_values=previous,
            changed_fields=changed,
        )

    def _snapshot(self, cattle: Cattle) -> dict:
        """Return a JSON-serialisable dict of current field values for audit logging."""
        return {
            "tag_number": cattle.tag_number,
            "name": cattle.name,
            "breed": cattle.breed,
            "date_of_birth": str(cattle.date_of_birth),
            "gender": cattle.gender,
            "weight_kg": str(cattle.weight_kg) if cattle.weight_kg is not None else None,
            "purchase_date": str(cattle.purchase_date) if cattle.purchase_date else None,
            "is_active": cattle.is_active,
            "notes": cattle.notes,
        }

    # ── Standard CRUD overrides for audit logging ─────────────────────────────

    def perform_create(self, serializer):
        """
        Save the new Cattle record and write a 'created' history entry.
        """
        cattle = serializer.save()
        self._record_history(
            cattle,
            action_type=AnimalHistory.ActionType.CREATED,
            previous={},
            changed=list(serializer.validated_data.keys()),
        )
        logger.info("Cattle created: %s by %s", cattle.tag_number, self.request.user)

    def perform_update(self, serializer):
        """
        Save the updated Cattle record and write an 'updated' history entry
        capturing previous values and the list of changed fields.
        """
        previous = self._snapshot(serializer.instance)
        cattle = serializer.save()
        changed_fields = list(serializer.validated_data.keys())
        self._record_history(
            cattle,
            action_type=AnimalHistory.ActionType.UPDATED,
            previous=previous,
            changed=changed_fields,
        )
        logger.info("Cattle updated: %s by %s", cattle.tag_number, self.request.user)

    def perform_destroy(self, instance):
        """
        Hard-delete the Cattle record and write a 'deleted' history entry.

        Note: prefer ``POST /api/cattle/{id}/deactivate/`` for reversible
        soft-deletes.  This action permanently removes the record.
        """
        previous = self._snapshot(instance)
        tag = instance.tag_number
        self._record_history(
            instance,
            action_type=AnimalHistory.ActionType.DELETED,
            previous=previous,
            changed=list(previous.keys()),
        )
        instance.delete()
        logger.info("Cattle hard-deleted: %s by %s", tag, self.request.user)

    # ── Custom action: milk history ───────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="milk-history")
    def milk_history(self, request, pk=None):
        """
        Return the last 30 days of MilkLog entries for a single cattle.

        GET /api/cattle/{id}/milk-history/

        Response body
        -------------
        {
            "cattle_id"    : int,
            "tag_number"   : str,
            "period_start" : "YYYY-MM-DD",
            "period_end"   : "YYYY-MM-DD",
            "total_litres" : float,      // sum across the period
            "avg_daily"    : float,      // average daily yield
            "logs"         : [
                {
                    "date"            : "YYYY-MM-DD",
                    "morning_litres"  : float,
                    "evening_litres"  : float,
                    "total_litres"    : float
                },
                ...
            ]
        }
        """
        cattle = self.get_object()
        period_end = date.today()
        period_start = period_end - timedelta(days=29)   # inclusive 30-day window

        logs_qs = (
            MilkLog.objects
            .filter(cattle=cattle, date__range=(period_start, period_end))
            .order_by("date")
            .values("date", "morning_litres", "evening_litres", "total_litres")
        )

        aggregates = logs_qs.aggregate(
            total=Sum("total_litres"),
            avg=Avg("total_litres"),
        )

        return Response(
            {
                "cattle_id": cattle.pk,
                "tag_number": cattle.tag_number,
                "period_start": str(period_start),
                "period_end": str(period_end),
                "total_litres": float(aggregates["total"] or 0),
                "avg_daily": round(float(aggregates["avg"] or 0), 2),
                "logs": [
                    {
                        "date": str(log["date"]),
                        "morning_litres": float(log["morning_litres"]),
                        "evening_litres": float(log["evening_litres"]),
                        "total_litres": float(log["total_litres"]),
                    }
                    for log in logs_qs
                ],
            },
            status=status.HTTP_200_OK,
        )

    # ── Custom action: health timeline ────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="health-timeline")
    def health_timeline(self, request, pk=None):
        """
        Return a merged, chronologically sorted timeline of all HealthAlerts
        and HealthRecords for a single cattle.

        GET /api/cattle/{id}/health-timeline/

        Query params
        ------------
        resolved : "true" | "false"
            Filter HealthAlerts by resolution status.  Omit to return all.

        Response body
        -------------
        {
            "cattle_id"  : int,
            "tag_number" : str,
            "timeline"   : [
                {
                    "event_type" : "alert" | "record",
                    "date"       : "YYYY-MM-DD",
                    // alert fields OR record fields depending on event_type
                },
                ...
            ]
        }
        """
        cattle = self.get_object()

        # ── Alerts ────────────────────────────────────────────────────────────
        alerts_qs = HealthAlert.objects.filter(cattle=cattle)
        resolved_param = request.query_params.get("resolved")
        if resolved_param is not None:
            alerts_qs = alerts_qs.filter(is_resolved=resolved_param.lower() == "true")

        alert_events = [
            {
                "event_type": "alert",
                "date": str(alert.alert_date),
                "alert_type": alert.alert_type,
                "severity": alert.severity,
                "message": alert.message,
                "is_resolved": alert.is_resolved,
                "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            }
            for alert in alerts_qs.order_by("-alert_date")
        ]

        # ── Vet records ───────────────────────────────────────────────────────
        record_events = [
            {
                "event_type": "record",
                "date": str(rec.record_date),
                "temperature": float(rec.temperature) if rec.temperature is not None else None,
                "symptoms": rec.symptoms,
                "treatment": rec.treatment,
                "vet_name": rec.vet_name,
            }
            for rec in HealthRecord.objects.filter(cattle=cattle).order_by("-record_date")
        ]

        # Merge and sort descending by date
        timeline = sorted(
            alert_events + record_events,
            key=lambda e: e["date"],
            reverse=True,
        )

        return Response(
            {
                "cattle_id": cattle.pk,
                "tag_number": cattle.tag_number,
                "timeline": timeline,
            },
            status=status.HTTP_200_OK,
        )

    # ── Custom action: dashboard stats ───────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="dashboard")
    def dashboard(self, request, pk=None):
        """
        Return a combined stats summary card for a single cattle.

        Designed to power a per-animal dashboard widget without requiring
        the frontend to make multiple API calls.

        GET /api/cattle/{id}/dashboard/

        Response body
        -------------
        {
            "cattle_id"              : int,
            "tag_number"             : str,
            "name"                   : str,
            "breed"                  : str,
            "age_years"              : float,
            "is_active"              : bool,
            "milk_last_30_days": {
                "total_litres"       : float,
                "avg_daily_litres"   : float,
                "latest_date"        : "YYYY-MM-DD" | null
            },
            "health": {
                "open_alerts"        : int,   // unresolved HealthAlerts
                "high_severity"      : int,   // HIGH severity open alerts
                "last_vet_visit"     : "YYYY-MM-DD" | null
            }
        }
        """
        from datetime import date as _date
        cattle = self.get_object()

        # ── Milk stats ────────────────────────────────────────────────────────
        period_start = _date.today() - timedelta(days=29)
        milk_agg = MilkLog.objects.filter(
            cattle=cattle, date__gte=period_start
        ).aggregate(
            total=Sum("total_litres"),
            avg=Avg("total_litres"),
            latest=Max("date"),
        )

        # ── Health stats ──────────────────────────────────────────────────────
        open_alerts = HealthAlert.objects.filter(cattle=cattle, is_resolved=False)
        last_record = (
            HealthRecord.objects.filter(cattle=cattle)
            .order_by("-record_date")
            .values_list("record_date", flat=True)
            .first()
        )

        # ── Age ───────────────────────────────────────────────────────────────
        from datetime import date as today_date
        age = round((_date.today() - cattle.date_of_birth).days / 365.25, 1)

        return Response(
            {
                "cattle_id": cattle.pk,
                "tag_number": cattle.tag_number,
                "name": cattle.name,
                "breed": cattle.breed,
                "age_years": age,
                "is_active": cattle.is_active,
                "milk_last_30_days": {
                    "total_litres": float(milk_agg["total"] or 0),
                    "avg_daily_litres": round(float(milk_agg["avg"] or 0), 2),
                    "latest_date": str(milk_agg["latest"]) if milk_agg["latest"] else None,
                },
                "health": {
                    "open_alerts": open_alerts.count(),
                    "high_severity": open_alerts.filter(
                        severity=HealthAlert.Severity.HIGH
                    ).count(),
                    "last_vet_visit": str(last_record) if last_record else None,
                },
            },
            status=status.HTTP_200_OK,
        )

    # ── Custom action: soft-delete ────────────────────────────────────────────

    @action(detail=True, methods=["post"], url_path="deactivate")
    def deactivate(self, request, pk=None):
        """
        Soft-delete a cattle record by setting ``is_active = False``.

        POST /api/cattle/{id}/deactivate/

        This is the preferred deletion method — the record and all related
        MilkLogs, HealthAlerts, and BreedingRecords are retained for auditing.
        To hard-delete, use DELETE /api/cattle/{id}/.

        Response body
        -------------
        { "detail": "Cattle <tag_number> has been deactivated." }

        Errors
        ------
        400  Returned if the cattle is already inactive.
        """
        cattle = self.get_object()

        if not cattle.is_active:
            return Response(
                {"detail": f"Cattle '{cattle.tag_number}' is already inactive."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        previous = self._snapshot(cattle)
        cattle.is_active = False
        cattle.save(update_fields=["is_active", "updated_at"])

        self._record_history(
            cattle,
            action_type=AnimalHistory.ActionType.UPDATED,
            previous=previous,
            changed=["is_active"],
        )
        logger.info("Cattle deactivated: %s by %s", cattle.tag_number, request.user)

        return Response(
            {"detail": f"Cattle '{cattle.tag_number}' has been deactivated."},
            status=status.HTTP_200_OK,
        )

    # ── Custom action: audit history ─────────────────────────────────────────

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, pk=None):
        """
        Return the full versioned audit log for a single cattle record,
        ordered from most recent to oldest.

        GET /api/cattle/{id}/history/

        Response body
        -------------
        [
            {
                "id"                  : int,
                "action_type"         : "created" | "updated" | "deleted",
                "changed_at"          : "ISO-8601 datetime",
                "changed_by_username" : str | null,
                "changed_fields"      : [str, ...],
                "previous_values"     : { field: value, ... }
            },
            ...
        ]
        """
        cattle = self.get_object()
        history_qs = (
            AnimalHistory.objects
            .filter(cattle=cattle)
            .select_related("changed_by")
            .order_by("-changed_at")
        )
        serializer = AnimalHistorySerializer(history_qs, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
