"""
Breeding Manager Celery tasks.

check_upcoming_heats
    Schedule : daily at 06:00 UTC (configured in settings.CELERY_BEAT_SCHEDULE)
    What     : Identifies cattle whose predicted next heat date falls within
               the next 3 days and creates BreedingAlert records.
               Full implementation delivered in the Breeding Manager feature task.

schedule_breeding_alerts
    Schedule : daily at 07:00 UTC
    What     : Iterates over all active female cattle with ≥ 2 heat logs,
               calls BreedingPredictor.predict_best_breeding_window(), and
               creates / updates a BEST_BREED_WINDOW BreedingAlert whenever
               the predicted best_ai_date falls within the next 3 days.
"""
import logging
from datetime import date, timedelta

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="breeding.tasks.check_upcoming_heats",
    max_retries=3,
    default_retry_delay=60,
    queue="health",
)
def check_upcoming_heats(self):
    """
    Daily at 06:00 UTC: scan HeatCycleLogs and BreedingPredictions for
    cattle whose next predicted heat falls within 3 days.

    Creates a BreedingAlert (HEAT_DUE) for each identified animal,
    deduplicating against alerts already sent within the past 24 hours.

    Returns
    -------
    dict  { "alerts_created": int }
    """
    try:
        logger.info("[check_upcoming_heats] Starting heat-window scan")
        # Full implementation delivered in the Breeding Manager feature task.
        return {"alerts_created": 0}
    except Exception as exc:
        logger.error("[check_upcoming_heats] Failed: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


@shared_task(
    bind=True,
    name="breeding.tasks.schedule_breeding_alerts",
    max_retries=3,
    default_retry_delay=60,
    queue="health",
)
def schedule_breeding_alerts(self):
    """
    Daily at 07:00 UTC: predict breeding windows for all active female
    cattle and create BEST_BREED_WINDOW alerts for those whose best AI date
    falls within the next 3 days.

    Algorithm
    ---------
    1. Fetch all active female Cattle records.
    2. For each cattle that has ≥ 2 HeatCycleLog entries, call
       BreedingPredictor.predict_best_breeding_window().
    3. If ``best_ai_date`` is within [today, today + 3 days], call
       BreedingAlert.objects.get_or_create() to create an unsent alert
       (idempotent — skips if an identical unsent alert already exists).
    4. Return a summary dict with alert counts.

    Returns
    -------
    dict
        {
            "cattle_scanned":  int,
            "alerts_created":  int,
            "errors":          int,
        }
    """
    from apps.cattle.models import Cattle
    from apps.breeding.models import BreedingAlert, HeatCycleLog
    from .ml.breeding_predictor import BreedingPredictor

    try:
        logger.info("[schedule_breeding_alerts] Starting daily breeding alert scan")

        today    = date.today()
        deadline = today + timedelta(days=3)

        # ── Active female cattle with at least 2 heat logs ────────────────────
        active_females = Cattle.objects.filter(
            gender=Cattle.Gender.FEMALE,
            is_active=True,
        )

        predictor       = BreedingPredictor()
        cattle_scanned  = 0
        alerts_created  = 0
        errors          = 0

        for cattle in active_females:
            # Quick pre-check: skip cattle with fewer than 2 heat logs to
            # avoid calling the predictor unnecessarily.
            heat_count = HeatCycleLog.objects.filter(cattle=cattle).count()
            if heat_count < 2:
                continue

            cattle_scanned += 1
            try:
                result = predictor.predict_best_breeding_window(cattle.pk)

                if "error" in result:
                    continue

                best_ai_date_str = result.get("best_ai_date", "")
                try:
                    best_ai_date = date.fromisoformat(best_ai_date_str)
                except ValueError:
                    logger.warning(
                        "[schedule_breeding_alerts] Invalid best_ai_date '%s' for cattle %s",
                        best_ai_date_str, cattle.tag_number,
                    )
                    continue

                if not (today <= best_ai_date <= deadline):
                    continue

                message = (
                    f"Best AI date for {cattle.tag_number} is {best_ai_date}. "
                    f"Optimal window: {result['optimal_window_start']} – "
                    f"{result['optimal_window_end']}. "
                    f"Avg cycle length: {result['avg_cycle_length_days']} days. "
                    f"Confidence: {result['confidence']}."
                )

                _, created = BreedingAlert.objects.get_or_create(
                    cattle=cattle,
                    alert_type=BreedingAlert.AlertType.BEST_BREED_WINDOW,
                    scheduled_date=best_ai_date,
                    is_sent=False,
                    defaults={"message": message},
                )
                if created:
                    alerts_created += 1
                    logger.info(
                        "[schedule_breeding_alerts] Alert created: cattle=%s date=%s",
                        cattle.tag_number, best_ai_date,
                    )

            except Exception as exc:
                errors += 1
                logger.error(
                    "[schedule_breeding_alerts] Error processing cattle %s: %s",
                    cattle.tag_number, exc, exc_info=True,
                )

        summary = {
            "cattle_scanned": cattle_scanned,
            "alerts_created": alerts_created,
            "errors":         errors,
        }
        logger.info("[schedule_breeding_alerts] Done: %s", summary)
        return summary

    except Exception as exc:
        logger.error("[schedule_breeding_alerts] Fatal error: %s", exc, exc_info=True)
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
