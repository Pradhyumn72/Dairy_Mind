"""
Health Alert API views.

AlertListView        GET  /api/alerts/                   Filterable alert list
AlertDetailView      GET  /api/alerts/{id}/               Single alert
AlertAcknowledgeView POST /api/alerts/{id}/acknowledge/   Resolve an alert
RunAnomalyCheckView  POST /api/alerts/run-check/          Trigger ML anomaly scan
"""
import logging
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import IsOwnerOrReadOnly, IsVetOrOwner
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import HealthAlert, HealthRecord

logger = logging.getLogger(__name__)


class AlertListView(APIView):
    """
    GET /api/alerts/

    Query params (all optional)
    ---------------------------
    is_resolved : bool  (?is_resolved=false | ?is_resolved=true)
    severity    : str   (?severity=HIGH | MEDIUM | LOW)
    cattle_id   : int   (?cattle_id=3)
    alert_type  : str   (?alert_type=ANOMALY | MANUAL | FORECAST)

    Response 200
    ------------
    {
        "count"  : int,
        "results": [ ...HealthAlert objects... ]
    }
    """
    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request):
        qs = HealthAlert.objects.select_related("cattle", "resolved_by").order_by("-created_at")

        # Filter: is_resolved
        is_resolved_param = request.query_params.get("is_resolved")
        if is_resolved_param is not None:
            is_resolved = is_resolved_param.lower() in ("true", "1", "yes")
            qs = qs.filter(is_resolved=is_resolved)

        # Filter: severity
        severity = request.query_params.get("severity")
        if severity:
            qs = qs.filter(severity=severity.upper())

        # Filter: cattle_id
        cattle_id = request.query_params.get("cattle_id")
        if cattle_id:
            try:
                qs = qs.filter(cattle_id=int(cattle_id))
            except (ValueError, TypeError):
                return Response(
                    {"detail": "cattle_id must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        # Filter: alert_type
        alert_type = request.query_params.get("alert_type")
        if alert_type:
            qs = qs.filter(alert_type=alert_type.upper())

        results = [
            {
                "id":           a.pk,
                "cattle_id":    a.cattle.pk,
                "tag_number":   a.cattle.tag_number,
                "cattle_name":  a.cattle.name,
                "alert_date":   str(a.alert_date),
                "alert_type":   a.alert_type,
                "severity":     a.severity,
                "message":      a.message,
                "is_resolved":  a.is_resolved,
                "resolved_at":  a.resolved_at.isoformat() if a.resolved_at else None,
                "created_at":   a.created_at.isoformat(),
            }
            for a in qs
        ]
        return Response({"count": len(results), "results": results})


class AlertDetailView(APIView):
    """GET /api/alerts/{id}/"""
    permission_classes = [IsOwnerOrReadOnly]

    def get(self, request, pk):
        alert = get_object_or_404(HealthAlert.objects.select_related("cattle"), pk=pk)
        return Response({
            "id":          alert.pk,
            "cattle_id":   alert.cattle.pk,
            "tag_number":  alert.cattle.tag_number,
            "alert_date":  str(alert.alert_date),
            "alert_type":  alert.alert_type,
            "severity":    alert.severity,
            "message":     alert.message,
            "is_resolved": alert.is_resolved,
            "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
            "created_at":  alert.created_at.isoformat(),
        })


class AlertAcknowledgeView(APIView):
    """POST /api/alerts/{id}/acknowledge/"""
    permission_classes = [IsOwnerOrReadOnly]

    def post(self, request, pk):
        alert = get_object_or_404(HealthAlert, pk=pk)

        if alert.is_resolved:
            return Response(
                {"detail": "Alert is already acknowledged/resolved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        alert.is_resolved = True
        alert.resolved_at = timezone.now()
        alert.resolved_by = request.user
        alert.save(update_fields=["is_resolved", "resolved_at", "resolved_by"])

        logger.info(
            "HealthAlert %d acknowledged by %s", pk, request.user
        )
        return Response(
            {"detail": "Alert acknowledged.", "alert_id": pk},
            status=status.HTTP_200_OK,
        )


class RunAnomalyCheckView(APIView):
    """
    Manually trigger the ML anomaly check for all active cattle.

    POST /api/alerts/run-check/

    Response 202
    ------------
    {
        "detail"  : "Anomaly check task enqueued.",
        "task_id" : str   // Celery task ID
    }
    """

    permission_classes = [IsOwnerOrReadOnly]

    def post(self, request):
        from .tasks import check_anomalies
        try:
            result = check_anomalies.apply_async()
            logger.info("[RunAnomalyCheckView] task enqueued: %s by %s", result.id, request.user)
            return Response(
                {"detail": "Anomaly check task enqueued.", "task_id": result.id},
                status=status.HTTP_202_ACCEPTED,
            )
        except Exception as exc:
            logger.exception("[RunAnomalyCheckView] failed to enqueue: %s", exc)
            return Response(
                {"detail": "Failed to enqueue anomaly check.", "error": str(exc)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
