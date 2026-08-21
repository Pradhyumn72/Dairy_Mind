"""
Vet Report Celery tasks.

summarize_vet_report(vet_report_id)
    Triggered asynchronously after a VetReport is created.
    Extracts text from the stored file, calls VetReportSummarizer, and
    persists the result (or error) back to the VetReport record.

Retry policy: 3 attempts with 60 / 120 / 240 second exponential backoff.
"""
import logging
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="vet_reports.tasks.summarize_vet_report",
    max_retries=3,
    default_retry_delay=60,
    queue="vet",
    soft_time_limit=4 * 60,   # Gemini calls should complete well under 4 min
    time_limit=5 * 60,
)
def summarize_vet_report(self, vet_report_id: int) -> dict:
    """
    Extract text from an uploaded vet report file and generate an AI summary.

    Workflow
    --------
    1. Fetch the VetReport record.
    2. Open the stored file from Django's media storage.
    3. Extract text via the appropriate extractor (PDF / TXT).
    4. If text is empty after extraction, mark as ``summary_failed`` with
       reason ``unextractable_content`` and return early.
    5. Call ``VetReportSummarizer.summarize()`` with the extracted text.
    6. Persist the summary and set status → ``summary_ready``.
    7. On any exception, set status → ``summary_failed`` with the error
       reason and re-raise so Celery can retry.

    Parameters
    ----------
    vet_report_id : int — PK of the VetReport record to process

    Returns
    -------
    dict  { "vet_report_id": int, "status": str }
    """
    from apps.vetreport.models import VetReport
    from apps.vetreport.ai.extractor import extract_text_from_file, ExtractionError
    from apps.vetreport.ai.summarizer import VetReportSummarizer

    logger.info("[summarize_vet_report] Starting for VetReport id=%d", vet_report_id)

    # ── 1. Fetch record ───────────────────────────────────────────────────────
    try:
        report = VetReport.objects.select_related("cattle").get(pk=vet_report_id)
    except VetReport.DoesNotExist:
        logger.error(
            "[summarize_vet_report] VetReport id=%d not found", vet_report_id
        )
        return {"vet_report_id": vet_report_id, "status": "not_found"}

    # Guard: skip if already processed (idempotency)
    if report.status != VetReport.Status.PENDING:
        logger.info(
            "[summarize_vet_report] VetReport id=%d already has status=%s, skipping",
            vet_report_id, report.status,
        )
        return {"vet_report_id": vet_report_id, "status": report.status}

    # ── 2 & 3. Extract text ───────────────────────────────────────────────────
    try:
        with report.file_path.open("rb") as fh:
            # Determine MIME type from the stored original filename extension
            fname = report.original_filename.lower()
            if fname.endswith(".pdf"):
                content_type = "application/pdf"
            else:
                content_type = "text/plain"

            raw_text = extract_text_from_file(fh, content_type)

    except ExtractionError as exc:
        logger.warning(
            "[summarize_vet_report] Extraction failed for VetReport id=%d: %s",
            vet_report_id, exc,
        )
        report.status       = VetReport.Status.FAILED
        report.error_reason = f"Text extraction failed: {exc}"
        report.processed_at = timezone.now()
        report.save(update_fields=["status", "error_reason", "processed_at"])
        return {"vet_report_id": vet_report_id, "status": "summary_failed"}

    except Exception as exc:
        logger.error(
            "[summarize_vet_report] Unexpected error opening file for VetReport id=%d: %s",
            vet_report_id, exc, exc_info=True,
        )
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

    # ── 4. Guard: empty text ──────────────────────────────────────────────────
    if not raw_text.strip():
        logger.warning(
            "[summarize_vet_report] No extractable text in VetReport id=%d", vet_report_id
        )
        report.status       = VetReport.Status.FAILED
        report.error_reason = "unextractable_content"
        report.processed_at = timezone.now()
        report.save(update_fields=["status", "error_reason", "processed_at"])
        return {"vet_report_id": vet_report_id, "status": "summary_failed"}

    # Persist extracted raw text for audit / re-processing
    report.raw_text = raw_text
    report.save(update_fields=["raw_text"])

    # ── 5. Summarise via Gemini ───────────────────────────────────────────────
    try:
        summarizer = VetReportSummarizer()
        summary    = summarizer.summarize(
            raw_text=raw_text,
            cattle_name=report.cattle.name,
        )
    except Exception as exc:
        logger.error(
            "[summarize_vet_report] Summarizer error for VetReport id=%d: %s",
            vet_report_id, exc, exc_info=True,
        )
        report.status       = VetReport.Status.FAILED
        report.error_reason = f"Gemini API error: {exc}"
        report.processed_at = timezone.now()
        report.save(update_fields=["status", "error_reason", "processed_at"])
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

    # ── 6. Persist summary ────────────────────────────────────────────────────
    report.ai_summary   = summary
    report.status       = VetReport.Status.READY
    report.error_reason = None
    report.processed_at = timezone.now()
    report.save(update_fields=["ai_summary", "status", "error_reason", "processed_at"])

    logger.info(
        "[summarize_vet_report] Done. VetReport id=%d → summary_ready (%d chars)",
        vet_report_id, len(summary),
    )
    return {"vet_report_id": vet_report_id, "status": "summary_ready"}
