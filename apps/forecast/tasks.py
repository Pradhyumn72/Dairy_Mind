"""
Celery tasks for the Forecast Engine.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="forecast.tasks.generate_all_forecasts",
    max_retries=3,
    default_retry_delay=60,
)
def generate_all_forecasts(self):
    """
    Nightly cron at 02:00 server time.
    Regenerates Prophet forecasts for all eligible Animals and the herd.
    """
    try:
        logger.info("Starting nightly forecast generation for all Animals")
        # Full implementation in the forecast feature task
    except Exception as exc:
        logger.error("Nightly forecast generation failed: %s", exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(
    bind=True,
    name="forecast.tasks.generate_single_forecast",
    max_retries=3,
    default_retry_delay=60,
)
def generate_single_forecast(self, animal_id: int):
    """
    Manual refresh triggered via POST /api/forecast/refresh/.
    Runs Prophet forecast for a single Animal and persists results.
    """
    try:
        logger.info("Generating forecast for Animal id=%s", animal_id)
        # Full implementation in the forecast feature task
    except Exception as exc:
        logger.error("Forecast generation failed for Animal id=%s: %s", animal_id, exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
