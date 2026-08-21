"""
Vet Report API views.

VetReportUploadView    POST /api/vet-reports/upload/
    Accepts multipart/form-data with ``cattle_id`` + ``file`` (PDF or TXT).
    Validates file type and size, persists the VetReport record, enqueues
    the summarisation Celery task, and returns 202 immediately.

VetReportDetailView    GET  /api/vet-reports/{id}/
    Returns the current status and (when ready) the AI summary.

VetReportListView      GET  /api/vet-reports/?cattle_id=<int>
    Returns a paginated list of VetReports, optionally filtered by cattle.
"""
import logging
import os

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from apps.accounts.permissions import IsOwnerOrReadOnly, IsVetOrOwner
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.cattle.models import Cattle
from .ai.extractor import ALLOWED_MIME_TYPES, MAX_FILE_SIZE_BYTES
from .models import VetReport

logger = logging.getLogger(__name__)

# Map file extensions to canonical MIME types for client-side extension tricks
_EXT_TO_MIME = {
    ".pdf": "application/pdf",
    ".txt": "text/plain",
}


def _resolve_content_type(file_obj) -> str:
    """
    Return the MIME type for an uploaded file.

    Prefers the extension-derived type over the browser-reported content_type
    because browsers occasionally misreport PDFs as 'application/octet-stream'.
    """
    ext = os.path.splitext(file_obj.name or "")[1].lower()
    if ext in _EXT_TO_MIME:
        return _EXT_TO_MIME[ext]
    return (file_obj.content_type or "").lower().split(";")[0].strip()


# ── Upload view ───────────────────────────────────────────────────────────────

class VetReportUploadView(APIView):
    """
    Upload a veterinary report PDF or TXT file and trigger AI summarisation.

    POST /api/vet-reports/upload/

    Request (multipart/form-data)
    -----------------------------
    cattle_id : int  (required) — PK of the Cattle this report belongs to
    file      : File (required) — PDF (.pdf) or plain text (.txt)

    Constraints
    -----------
    * Allowed MIME types: application/pdf, text/plain
    * Maximum file size: 10 MB
    * Cattle must exist and be active

    Response 202 — report accepted, summarisation queued
    ----------------------------------------------------
    {
        "report_id"    : int,
        "cattle_id"    : int,
        "tag_number"   : str,
        "filename"     : str,
        "status"       : "pending_summarization",
        "detail"       : "Report uploaded. AI summarisation is in progress.",
        "poll_url"     : "/api/vet-reports/{id}/"
    }

    Response 400 — validation error
    Response 404 — cattle not found
    Response 413 — file too large
    Response 415 — unsupported file type
    """

    permission_classes = [IsVetOrOwner]
    parser_classes     = [MultiPartParser, FormParser]

    def post(self, request):
        # ── Validate cattle_id ────────────────────────────────────────────────
        cattle_id = request.data.get("cattle_id")
        if not cattle_id:
            return Response(
                {"detail": "cattle_id is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            cattle_id = int(cattle_id)
        except (TypeError, ValueError):
            return Response(
                {"detail": "cattle_id must be an integer."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        cattle = get_object_or_404(Cattle, pk=cattle_id)

        # ── Validate file presence ────────────────────────────────────────────
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response(
                {"detail": "A file is required. Send it as multipart field 'file'."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── File size check (10 MB) ───────────────────────────────────────────
        if uploaded_file.size > MAX_FILE_SIZE_BYTES:
            max_mb = MAX_FILE_SIZE_BYTES // (1024 * 1024)
            return Response(
                {
                    "detail": (
                        f"File size {uploaded_file.size / (1024*1024):.1f} MB "
                        f"exceeds the maximum allowed size of {max_mb} MB."
                    )
                },
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        # ── MIME type check ───────────────────────────────────────────────────
        content_type = _resolve_content_type(uploaded_file)
        if content_type not in ALLOWED_MIME_TYPES:
            return Response(
                {
                    "detail": (
                        f"File type '{content_type}' is not supported. "
                        "Please upload a PDF (.pdf) or plain-text (.txt) file."
                    )
                },
                status=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            )

        # ── Persist VetReport record ──────────────────────────────────────────
        report = VetReport.objects.create(
            cattle=cattle,
            uploaded_by=request.user,
            original_filename=uploaded_file.name,
            file_path=uploaded_file,
            status=VetReport.Status.PENDING,
        )

        logger.info(
            "[VetReportUploadView] VetReport id=%d created for cattle=%s by user=%s",
            report.pk, cattle.tag_number, request.user,
        )

        # ── Enqueue summarisation task (async — does NOT block this response) ─
        from .tasks import summarize_vet_report
        summarize_vet_report.apply_async(
            args=[report.pk],
            countdown=2,   # tiny delay to let the DB transaction commit
        )

        return Response(
            {
                "report_id":  report.pk,
                "cattle_id":  cattle.pk,
                "tag_number": cattle.tag_number,
                "filename":   report.original_filename,
                "status":     report.status,
                "detail":     "Report uploaded. AI summarisation is in progress.",
                "poll_url":   f"/api/vet-reports/{report.pk}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ── Detail view ───────────────────────────────────────────────────────────────

class VetReportDetailView(APIView):
    """
    Retrieve the current status and AI summary of a single VetReport.

    GET /api/vet-reports/{id}/

    Response 200
    ------------
    {
        "id"              : int,
        "cattle_id"       : int,
        "tag_number"      : str,
        "cattle_name"     : str,
        "original_filename": str,
        "status"          : "pending_summarization" | "summary_ready" | "summary_failed",
        "ai_summary"      : str | null,
        "error_reason"    : str | null,
        "upload_date"     : "ISO-8601",
        "processed_at"    : "ISO-8601" | null
    }

    Response 404 — report not found
    """

    permission_classes = [IsVetOrOwner]

    def get(self, request, pk: int):
        report = get_object_or_404(
            VetReport.objects.select_related("cattle", "uploaded_by"),
            pk=pk,
        )
        return Response(
            {
                "id":                report.pk,
                "cattle_id":         report.cattle.pk,
                "tag_number":        report.cattle.tag_number,
                "cattle_name":       report.cattle.name,
                "original_filename": report.original_filename,
                "status":            report.status,
                "ai_summary":        report.ai_summary,
                "error_reason":      report.error_reason,
                "upload_date":       report.upload_date.isoformat(),
                "processed_at":      report.processed_at.isoformat() if report.processed_at else None,
            },
            status=status.HTTP_200_OK,
        )


# ── List view ─────────────────────────────────────────────────────────────────

class VetReportListView(APIView):
    """
    List VetReports, optionally filtered by cattle.

    GET /api/vet-reports/?cattle_id=<int>

    Query params
    ------------
    cattle_id : int (optional) — filter to a specific cattle

    Response 200
    ------------
    {
        "count"  : int,
        "results": [ ...VetReport objects... ]
    }
    """

    permission_classes = [IsVetOrOwner]

    def get(self, request):
        qs = VetReport.objects.select_related("cattle").order_by("-upload_date")

        cattle_id = request.query_params.get("cattle_id")
        if cattle_id:
            try:
                qs = qs.filter(cattle_id=int(cattle_id))
            except (TypeError, ValueError):
                return Response(
                    {"detail": "cattle_id must be an integer."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        results = [
            {
                "id":                r.pk,
                "cattle_id":         r.cattle.pk,
                "tag_number":        r.cattle.tag_number,
                "cattle_name":       r.cattle.name,
                "original_filename": r.original_filename,
                "status":            r.status,
                "ai_summary":        r.ai_summary,
                "upload_date":       r.upload_date.isoformat(),
                "processed_at":      r.processed_at.isoformat() if r.processed_at else None,
            }
            for r in qs
        ]

        return Response(
            {"count": len(results), "results": results},
            status=status.HTTP_200_OK,
        )
