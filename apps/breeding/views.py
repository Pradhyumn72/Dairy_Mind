"""
Breeding Manager ViewSets and standalone API views.

ViewSets
--------
HeatCycleLogViewSet            CRUD + filter by cattle / date range
ArtificialInseminationViewSet  CRUD + POST /{id}/mark-outcome/
PregnancyRecordViewSet         CRUD + POST /{id}/record-calving/
BreedingAlertViewSet           list/retrieve + POST /{id}/mark-sent/

Standalone views
----------------
CattleReproductiveTimelineView  GET /api/breeding/cattle/{id}/timeline/
DueThisWeekView                 GET /api/breeding/due-this-week/
PendingAlertsView               GET /api/breeding/alerts/pending/
PredictBreedingWindowView       GET /api/breeding/cattle/{id}/predict-breeding/
AISuccessProbabilityView        GET /api/breeding/cattle/{id}/ai-success-prob/
"""
import logging
from datetime import date, timedelta

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import IsOwnerOrReadOnly, IsVetOrOwner
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cattle.models import Cattle

from .filters import (
    ArtificialInseminationFilter,
    BreedingAlertFilter,
    HeatCycleLogFilter,
    PregnancyRecordFilter,
)
from .models import (
    ArtificialInsemination,
    BreedingAlert,
    HeatCycleLog,
    PregnancyRecord,
)
from .serializers import (
    ArtificialInseminationSerializer,
    BreedingAlertSerializer,
    HeatCycleLogSerializer,
    PregnancyRecordSerializer,
)

logger = logging.getLogger(__name__)


# ── HeatCycleLogViewSet ───────────────────────────────────────────────────────

class HeatCycleLogViewSet(viewsets.ModelViewSet):
    """
    ViewSet for HeatCycleLog records.

    list     GET    /api/breeding/heat-cycles/          Paginated, filterable list.
    create   POST   /api/breeding/heat-cycles/          Record a new heat event.
    retrieve GET    /api/breeding/heat-cycles/{id}/     Single record detail.
    update   PUT    /api/breeding/heat-cycles/{id}/     Full update.
    partial  PATCH  /api/breeding/heat-cycles/{id}/     Partial update.
    destroy  DELETE /api/breeding/heat-cycles/{id}/     Delete.

    Filters: cattle (PK), date_from, date_to, intensity
    Search : cattle__tag_number, cattle__name
    Order  : observed_date, intensity
    """

    queryset = (
        HeatCycleLog.objects
        .select_related("cattle", "recorded_by")
        .order_by("-observed_date")
    )
    serializer_class  = HeatCycleLogSerializer
    permission_classes = [IsOwnerOrReadOnly]
    filter_backends   = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class   = HeatCycleLogFilter
    search_fields     = ["cattle__tag_number", "cattle__name"]
    ordering_fields   = ["observed_date", "intensity"]
    ordering          = ["-observed_date"]

    def perform_create(self, serializer):
        """Set recorded_by to the current authenticated user on creation."""
        log = serializer.save(recorded_by=self.request.user)
        logger.info(
            "HeatCycleLog created: cattle=%s date=%s intensity=%s by=%s",
            log.cattle.tag_number, log.observed_date, log.intensity, self.request.user,
        )


# ── ArtificialInseminationViewSet ─────────────────────────────────────────────

class ArtificialInseminationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for ArtificialInsemination records.

    Standard CRUD routes are router-generated.

    Custom actions
    --------------
    POST /api/breeding/ai/{id}/mark-outcome/
        Set the outcome of an AI event to CONFIRMED_PREGNANT or FAILED.
        If CONFIRMED_PREGNANT, a PregnancyRecord is auto-created with
        expected_calving_date = ai_date + 280 days (unless one already exists).

    Filters: cattle (PK), date_from, date_to, outcome
    Search : cattle__tag_number, semen_bull_name, technician_name
    Order  : ai_date, outcome
    """

    queryset = (
        ArtificialInsemination.objects
        .select_related("cattle")
        .order_by("-ai_date")
    )
    serializer_class  = ArtificialInseminationSerializer
    permission_classes = [IsOwnerOrReadOnly]
    filter_backends   = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class   = ArtificialInseminationFilter
    search_fields     = ["cattle__tag_number", "semen_bull_name", "technician_name"]
    ordering_fields   = ["ai_date", "outcome"]
    ordering          = ["-ai_date"]

    @action(detail=True, methods=["post"], url_path="mark-outcome")
    def mark_outcome(self, request, pk=None):
        """
        Set the outcome of an AI event.

        POST /api/breeding/ai/{id}/mark-outcome/

        Request body
        ------------
        {
            "outcome": "CONFIRMED_PREGNANT" | "FAILED"
        }

        Behaviour
        ---------
        * CONFIRMED_PREGNANT → updates outcome and auto-creates a
          PregnancyRecord (idempotent: skipped if one already exists for this
          ai_event).  Returns the created/existing PregnancyRecord in the
          response.
        * FAILED → updates outcome only.
        * PENDING is not accepted — use the regular PATCH endpoint to reset.

        Response 200 (CONFIRMED_PREGNANT)
        ----------------------------------
        {
            "detail"           : "Outcome updated to CONFIRMED_PREGNANT.",
            "ai_event"         : { ...ArtificialInseminationSerializer... },
            "pregnancy_created": bool,
            "pregnancy"        : { ...PregnancyRecordSerializer... }
        }

        Response 200 (FAILED)
        ---------------------
        {
            "detail"  : "Outcome updated to FAILED.",
            "ai_event": { ...ArtificialInseminationSerializer... }
        }

        Response 400  — invalid/missing outcome or already-finalised event.
        """
        ai_event = self.get_object()
        new_outcome = request.data.get("outcome")

        # Validate the submitted outcome
        allowed = [
            ArtificialInsemination.Outcome.CONFIRMED_PREGNANT,
            ArtificialInsemination.Outcome.FAILED,
        ]
        if new_outcome not in allowed:
            return Response(
                {
                    "detail": (
                        f"Invalid outcome '{new_outcome}'. "
                        f"Allowed values: {allowed}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Guard against re-finalising an already-decided event
        if ai_event.outcome != ArtificialInsemination.Outcome.PENDING:
            return Response(
                {
                    "detail": (
                        f"This AI event outcome is already '{ai_event.outcome}'. "
                        "Only PENDING events can be finalised."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            ai_event.outcome = new_outcome
            ai_event.save(update_fields=["outcome", "updated_at"])

            if new_outcome == ArtificialInsemination.Outcome.CONFIRMED_PREGNANT:
                pregnancy, created = PregnancyRecord.objects.get_or_create(
                    ai_event=ai_event,
                    defaults={
                        "cattle": ai_event.cattle,
                        "confirmed_date": ai_event.ai_date,
                        # expected_calving_date auto-set by model.save() to +280 days
                    },
                )
                logger.info(
                    "AI event %s → CONFIRMED_PREGNANT; pregnancy %s (created=%s)",
                    ai_event.pk, pregnancy.pk, created,
                )
                return Response(
                    {
                        "detail": "Outcome updated to CONFIRMED_PREGNANT.",
                        "ai_event": ArtificialInseminationSerializer(ai_event).data,
                        "pregnancy_created": created,
                        "pregnancy": PregnancyRecordSerializer(pregnancy).data,
                    },
                    status=status.HTTP_200_OK,
                )

        logger.info("AI event %s → FAILED", ai_event.pk)
        return Response(
            {
                "detail": "Outcome updated to FAILED.",
                "ai_event": ArtificialInseminationSerializer(ai_event).data,
            },
            status=status.HTTP_200_OK,
        )


# ── PregnancyRecordViewSet ────────────────────────────────────────────────────

class PregnancyRecordViewSet(viewsets.ModelViewSet):
    """
    ViewSet for PregnancyRecord.

    Standard CRUD routes are router-generated.

    Custom actions
    --------------
    POST /api/breeding/pregnancy/{id}/record-calving/
        Records the actual calving outcome and closes the pregnancy.

    Filters: cattle (PK), is_active
    Search : cattle__tag_number, cattle__name
    Order  : confirmed_date, expected_calving_date
    """

    queryset = (
        PregnancyRecord.objects
        .select_related("cattle", "ai_event")
        .order_by("-confirmed_date")
    )
    serializer_class  = PregnancyRecordSerializer
    permission_classes = [IsOwnerOrReadOnly]
    filter_backends   = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_class   = PregnancyRecordFilter
    search_fields     = ["cattle__tag_number", "cattle__name"]
    ordering_fields   = ["confirmed_date", "expected_calving_date"]
    ordering          = ["-confirmed_date"]

    @action(detail=True, methods=["post"], url_path="record-calving")
    def record_calving(self, request, pk=None):
        """
        Record the actual calving outcome and close the pregnancy.

        POST /api/breeding/pregnancy/{id}/record-calving/

        Request body
        ------------
        {
            "actual_calving_date" : "YYYY-MM-DD"  (required),
            "calf_gender"         : "Male" | "Female" | "Unknown"  (optional)
        }

        Behaviour
        ---------
        * Sets actual_calving_date and calf_gender on the PregnancyRecord.
        * Sets is_active = False (pregnancy concluded).
        * actual_calving_date must not be in the future.
        * Returns 400 if the pregnancy is already closed (is_active=False).

        Response 200
        ------------
        {
            "detail"   : "Calving recorded successfully.",
            "pregnancy": { ...PregnancyRecordSerializer... }
        }

        Response 400  — validation error or already-closed pregnancy.
        """
        pregnancy = self.get_object()

        if not pregnancy.is_active:
            return Response(
                {"detail": "This pregnancy is already closed (calving already recorded)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        calving_date_raw = request.data.get("actual_calving_date")
        calf_gender      = request.data.get("calf_gender")

        if not calving_date_raw:
            return Response(
                {"detail": "actual_calving_date is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse and validate the calving date
        from datetime import date as _date
        try:
            from datetime import date as _date
            calving_date = _date.fromisoformat(str(calving_date_raw))
        except ValueError:
            return Response(
                {"detail": f"Invalid date format '{calving_date_raw}'. Use YYYY-MM-DD."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if calving_date > _date.today():
            return Response(
                {"detail": "actual_calving_date cannot be in the future."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if calving_date < pregnancy.confirmed_date:
            return Response(
                {"detail": "actual_calving_date cannot be before confirmed_date."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Validate optional calf_gender
        valid_genders = [c[0] for c in PregnancyRecord.CalfGender.choices]
        if calf_gender and calf_gender not in valid_genders:
            return Response(
                {
                    "detail": (
                        f"Invalid calf_gender '{calf_gender}'. "
                        f"Allowed: {valid_genders}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        pregnancy.actual_calving_date = calving_date
        pregnancy.calf_gender         = calf_gender or PregnancyRecord.CalfGender.UNKNOWN
        pregnancy.is_active           = False
        pregnancy.save(update_fields=["actual_calving_date", "calf_gender", "is_active", "updated_at"])

        logger.info(
            "Calving recorded: pregnancy=%s cattle=%s date=%s calf_gender=%s",
            pregnancy.pk, pregnancy.cattle.tag_number, calving_date, pregnancy.calf_gender,
        )

        return Response(
            {
                "detail": "Calving recorded successfully.",
                "pregnancy": PregnancyRecordSerializer(pregnancy).data,
            },
            status=status.HTTP_200_OK,
        )


# ── BreedingAlertViewSet ──────────────────────────────────────────────────────

class BreedingAlertViewSet(viewsets.ReadOnlyModelViewSet):
    """
    ViewSet for BreedingAlert (read-only list/retrieve + mark-sent action).

    Standard read routes are router-generated.

    Custom actions
    --------------
    POST /api/breeding/breeding-alerts/{id}/mark-sent/
        Marks a BreedingAlert as sent (is_sent=True).
        Returns 400 if already marked sent.

    Filters: cattle (PK), is_sent, alert_type
    Order  : scheduled_date
    """

    queryset = (
        BreedingAlert.objects
        .select_related("cattle")
        .order_by("scheduled_date")
    )
    serializer_class  = BreedingAlertSerializer
    permission_classes = [IsOwnerOrReadOnly]
    filter_backends   = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_class   = BreedingAlertFilter
    ordering_fields   = ["scheduled_date", "alert_type"]
    ordering          = ["scheduled_date"]

    @action(detail=True, methods=["post"], url_path="mark-sent")
    def mark_sent(self, request, pk=None):
        """
        Mark a BreedingAlert as sent.

        POST /api/breeding/breeding-alerts/{id}/mark-sent/

        Response 200
        ------------
        { "detail": "Alert marked as sent.", "alert": { ... } }

        Response 400
        ------------
        { "detail": "Alert is already marked as sent." }
        """
        alert = self.get_object()

        if alert.is_sent:
            return Response(
                {"detail": "Alert is already marked as sent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        alert.is_sent = True
        alert.save(update_fields=["is_sent"])
        logger.info(
            "BreedingAlert %s marked sent: cattle=%s type=%s",
            alert.pk, alert.cattle.tag_number, alert.alert_type,
        )
        return Response(
            {
                "detail": "Alert marked as sent.",
                "alert": BreedingAlertSerializer(alert).data,
            },
            status=status.HTTP_200_OK,
        )


# ── Standalone views ──────────────────────────────────────────────────────────

class CattleReproductiveTimelineView(APIView):
    """
    Return the full reproductive history for a single cattle as a
    chronologically sorted timeline merging heat logs, AI events, and
    pregnancy records.

    GET /api/breeding/cattle/{cattle_id}/timeline/

    Response 200
    ------------
    {
        "cattle_id"  : int,
        "tag_number" : str,
        "name"       : str,
        "timeline"   : [
            {
                "event_type" : "heat_cycle" | "ai_event" | "pregnancy",
                "date"       : "YYYY-MM-DD",
                // ... event-type-specific fields
            },
            ...                           // sorted ascending by date
        ]
    }

    Response 404  — Cattle not found.
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request, cattle_id: int):
        cattle = get_object_or_404(Cattle, pk=cattle_id)

        # ── Heat cycles ───────────────────────────────────────────────────────
        heat_events = [
            {
                "event_type":    "heat_cycle",
                "date":          str(h.observed_date),
                "intensity":     h.intensity,
                "signs":         h.signs,
                "id":            h.pk,
            }
            for h in HeatCycleLog.objects.filter(cattle=cattle).order_by("observed_date")
        ]

        # ── AI events ─────────────────────────────────────────────────────────
        ai_events = [
            {
                "event_type":       "ai_event",
                "date":             str(a.ai_date),
                "semen_bull_name":  a.semen_bull_name,
                "semen_batch_id":   a.semen_batch_id,
                "technician_name":  a.technician_name,
                "outcome":          a.outcome,
                "id":               a.pk,
            }
            for a in ArtificialInsemination.objects.filter(cattle=cattle).order_by("ai_date")
        ]

        # ── Pregnancies ───────────────────────────────────────────────────────
        pregnancy_events = [
            {
                "event_type":           "pregnancy",
                "date":                 str(p.confirmed_date),
                "expected_calving":     str(p.expected_calving_date),
                "actual_calving":       str(p.actual_calving_date) if p.actual_calving_date else None,
                "calf_gender":          p.calf_gender,
                "is_active":            p.is_active,
                "id":                   p.pk,
            }
            for p in PregnancyRecord.objects.filter(cattle=cattle).order_by("confirmed_date")
        ]

        # Merge and sort ascending by date
        timeline = sorted(
            heat_events + ai_events + pregnancy_events,
            key=lambda e: e["date"],
        )

        return Response(
            {
                "cattle_id":  cattle.pk,
                "tag_number": cattle.tag_number,
                "name":       cattle.name,
                "timeline":   timeline,
            },
            status=status.HTTP_200_OK,
        )


class DueThisWeekView(APIView):
    """
    Return all active pregnancies whose expected_calving_date falls within
    the next 7 calendar days (today through today + 6 inclusive).

    GET /api/breeding/due-this-week/

    Response 200
    ------------
    {
        "period_start" : "YYYY-MM-DD",
        "period_end"   : "YYYY-MM-DD",
        "count"        : int,
        "pregnancies"  : [ ...PregnancyRecordSerializer... ]
    }
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        today    = date.today()
        week_end = today + timedelta(days=6)

        qs = (
            PregnancyRecord.objects
            .filter(
                is_active=True,
                expected_calving_date__range=(today, week_end),
            )
            .select_related("cattle", "ai_event")
            .order_by("expected_calving_date")
        )

        return Response(
            {
                "period_start": str(today),
                "period_end":   str(week_end),
                "count":        qs.count(),
                "pregnancies":  PregnancyRecordSerializer(qs, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


class PendingAlertsView(APIView):
    """
    Return all BreedingAlerts that have not yet been sent (is_sent=False),
    sorted ascending by scheduled_date so the most imminent alerts appear first.

    GET /api/breeding/alerts/pending/

    Response 200
    ------------
    {
        "count"  : int,
        "alerts" : [ ...BreedingAlertSerializer... ]
    }
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        qs = (
            BreedingAlert.objects
            .filter(is_sent=False)
            .select_related("cattle")
            .order_by("scheduled_date")
        )

        return Response(
            {
                "count":  qs.count(),
                "alerts": BreedingAlertSerializer(qs, many=True).data,
            },
            status=status.HTTP_200_OK,
        )


# ── ML Prediction views ───────────────────────────────────────────────────────

class PredictBreedingWindowView(APIView):
    """
    Predict the optimal breeding window for a cattle using ML.

    GET /api/breeding/cattle/{cattle_id}/predict-breeding/

    Response 200 — success
    ----------------------
    {
        "predicted_next_heat":   "YYYY-MM-DD",
        "best_ai_date":          "YYYY-MM-DD",
        "optimal_window_start":  "YYYY-MM-DDTHH:MM",
        "optimal_window_end":    "YYYY-MM-DDTHH:MM",
        "avg_cycle_length_days": float,
        "cycles_analyzed":       int,
        "confidence":            "LOW" | "MEDIUM" | "HIGH",
        "alert_created":         bool     # True when best_ai_date is within 5 days
    }

    Response 200 — insufficient data
    ---------------------------------
    { "error": "insufficient_data", "cycles_found": N }

    Response 404  — Cattle not found.
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request, cattle_id: int):
        cattle = get_object_or_404(Cattle, pk=cattle_id)

        from .ml.breeding_predictor import BreedingPredictor
        predictor = BreedingPredictor()
        result    = predictor.predict_best_breeding_window(cattle_id)

        alert_created = False
        if "error" not in result:
            alert_created = _maybe_create_breeding_alert(
                cattle=cattle,
                best_ai_date_str=result["best_ai_date"],
                days_window=5,
                message=(
                    f"Optimal AI window for {cattle.tag_number}: "
                    f"{result['optimal_window_start']} – {result['optimal_window_end']}. "
                    f"Confidence: {result['confidence']}."
                ),
            )
            result["alert_created"] = alert_created
        else:
            result["alert_created"] = False

        logger.info(
            "[predict-breeding] cattle=%s result=%s alert_created=%s",
            cattle_id, result.get("confidence", result.get("error")), alert_created,
        )
        return Response(result, status=status.HTTP_200_OK)


class AISuccessProbabilityView(APIView):
    """
    Estimate the AI success probability for a cattle.

    GET /api/breeding/cattle/{cattle_id}/ai-success-prob/

    Response 200
    ------------
    {
        "success_probability": float (0.0–1.0),
        "success_percent":     int,
        "confidence":          "HEURISTIC" | "MODEL",
        "key_factors":         [str, ...],
        "recommendation":      str,
        "alert_created":       bool   # True when a breeding window alert was also triggered
    }

    Response 404  — Cattle not found.
    """

    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request, cattle_id: int):
        cattle = get_object_or_404(Cattle, pk=cattle_id)

        from .ml.breeding_predictor import BreedingPredictor
        predictor = BreedingPredictor()
        result    = predictor.predict_ai_success_probability(cattle_id)

        if "error" in result:
            return Response(result, status=status.HTTP_200_OK)

        # Also run the window predictor so we can emit an alert if imminent
        window = predictor.predict_best_breeding_window(cattle_id)
        alert_created = False
        if "error" not in window:
            alert_created = _maybe_create_breeding_alert(
                cattle=cattle,
                best_ai_date_str=window["best_ai_date"],
                days_window=5,
                message=(
                    f"AI success probability for {cattle.tag_number}: "
                    f"{result['success_percent']}% ({result['confidence']}). "
                    f"Optimal window: {window.get('optimal_window_start', 'N/A')} – "
                    f"{window.get('optimal_window_end', 'N/A')}."
                ),
            )
        result["alert_created"] = alert_created

        logger.info(
            "[ai-success-prob] cattle=%s prob=%s confidence=%s alert_created=%s",
            cattle_id, result["success_probability"], result["confidence"], alert_created,
        )
        return Response(result, status=status.HTTP_200_OK)


# ── Shared alert helper ───────────────────────────────────────────────────────

def _maybe_create_breeding_alert(
    cattle,
    best_ai_date_str: str,
    days_window: int,
    message: str,
) -> bool:
    """
    Create a BEST_BREED_WINDOW BreedingAlert if best_ai_date falls within
    *days_window* days from today.

    Idempotent: does not create a duplicate if an unsent alert for the same
    cattle / scheduled_date already exists.

    Returns True when a new alert was created, False otherwise.
    """
    try:
        best_ai_date = date.fromisoformat(best_ai_date_str)
    except ValueError:
        logger.warning("_maybe_create_breeding_alert: invalid date '%s'", best_ai_date_str)
        return False

    today    = date.today()
    deadline = today + timedelta(days=days_window)

    if not (today <= best_ai_date <= deadline):
        return False

    _, created = BreedingAlert.objects.get_or_create(
        cattle=cattle,
        alert_type=BreedingAlert.AlertType.BEST_BREED_WINDOW,
        scheduled_date=best_ai_date,
        is_sent=False,
        defaults={"message": message},
    )
    if created:
        logger.info(
            "BreedingAlert BEST_BREED_WINDOW created: cattle=%s date=%s",
            cattle.tag_number, best_ai_date,
        )
    return created
