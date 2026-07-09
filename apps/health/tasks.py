"""
Celery tasks for the Health Alert Engine.
"""
import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="health.tasks.run_anomaly_detection",
    max_retries=3,
    default_retry_delay=60,
)
def run_anomaly_detection(self, milk_log_id: int):
    """
    Triggered: post-save signal on MilkLog.
    Evaluates the new yield against the Animal's Isolation Forest model.
    Creates an Alert if the yield is classified as anomalous.
    """
    try:
        logger.info("Running anomaly detection for MilkLog id=%s", milk_log_id)
        # Full implementation in the health alerts feature task
    except Exception as exc:
        logger.error("Anomaly detection failed for MilkLog id=%s: %s", milk_log_id, exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(
    bind=True,
    name="health.tasks.retrain_isolation_forest",
    max_retries=3,
    default_retry_delay=60,
)
def retrain_isolation_forest(self, animal_id: int):
    """
    Triggered: when an Animal accumulates 50 new MilkLogs since last training.
    Retrains and persists the Isolation Forest model for the given Animal.
    """
    try:
        logger.info("Retraining Isolation Forest for Animal id=%s", animal_id)
        # Full implementation in the health alerts feature task
    except Exception as exc:
        logger.error("Retraining failed for Animal id=%s: %s", animal_id, exc)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
