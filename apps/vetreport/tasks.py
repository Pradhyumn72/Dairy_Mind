"""
Celery task for the Vet Report AI Summarizer.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="vet_reports.tasks.summarize_vet_report",
    max_retries=3,
    default_retry_delay=60,
)
def summarize_vet_report(self, vet_report_id: int):
    """
    Triggered: post-save signal on VetReport (status=pending_summarization).
    Extracts text from PDF/TXT, calls Gemini API, persists summary or error.
    """
    try:
        logger.info("Starting summarization for VetReport id=%s", vet_report_id)
        # Full implementation in the vet report AI feature task
    except Exception as exc:
        logger.error("Summarization failed for VetReport id=%s: %s", vet_report_id, exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
