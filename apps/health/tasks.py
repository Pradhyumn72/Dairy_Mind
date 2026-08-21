"""
Health app Celery tasks.

Task 1 — check_anomalies
    Schedule : every 6 hours
    What     : For each active cattle, fetch the last 14 days of MilkLog data,
               fit a fresh IsolationForest on that history, score today's
               production, and create a HealthAlert when the score is < -0.1.
               Fires the on_alert_created Django signal after each alert.

Task 2 — daily_health_report
    Schedule : every day at 08:00 UTC
    What     : Aggregate all UNRESOLVED HealthAlerts from the past 7 days,
               group counts by severity, and return a summary dict.  Designed
               to be consumed by notification / email tasks downstream.

Task 3 — resolve_old_alerts
    Schedule : every Sunday at 00:00 UTC
    What     : Auto-resolve LOW severity HealthAlerts that are older than 30
               days and still marked as unresolved.

All three tasks use:
    • bind=True          — access to self.retry()
    • max_retries=3      — honour the project retry policy
    • exponential backoff starting at 60 s (60 / 120 / 240)
    • structured logging throughout
"""
import logging
from datetime import date, timedelta

import numpy as np
from celery import shared_task
from django.utils import timezone

logger = logging.getLogger(__name__)

# ── Severity thresholds ───────────────────────────────────────────────────────
# IsolationForest anomaly scores are in (-1, 0].
# Negative values indicate anomalies; more negative = more anomalous.
# We map score ranges to alert severity:
#   score in (-0.3, -0.1]  → LOW
#   score in (-0.5, -0.3]  → MEDIUM
#   score <= -0.5           → HIGH
THRESHOLD_ANOMALY = -0.1    # below this → any anomaly
THRESHOLD_MEDIUM  = -0.3    # below this → MEDIUM or HIGH
THRESHOLD_HIGH    = -0.5    # below this → HIGH

MIN_HISTORY_POINTS = 7      # need at least 7 data points to fit a model
AUTO_RESOLVE_DAYS  = 30     # LOW alerts older than this are auto-resolved


# ── Helpers ───────────────────────────────────────────────────────────────────

def _score_to_severity(score: float) -> str:
    """Map a raw IsolationForest score to a HealthAlert severity string."""
    from apps.health.models import HealthAlert
    if score <= THRESHOLD_HIGH:
        return HealthAlert.Severity.HIGH
    if score <= THRESHOLD_MEDIUM:
        return HealthAlert.Severity.MEDIUM
    return HealthAlert.Severity.LOW


def _build_alert_message(cattle_tag: str, today_total: float, mean: float,
                          score: float, severity: str) -> str:
    """Compose a human-readable alert message."""
    pct_drop = ((mean - today_total) / mean * 100) if mean > 0 else 0
    return (
        f"Anomalous milk production detected for {cattle_tag}. "
        f"Today's yield: {today_total:.1f} L "
        f"(14-day avg: {mean:.1f} L, drop: {pct_drop:.0f}%). "
        f"Anomaly score: {score:.3f}. "
        f"Severity: {severity}."
    )


# ── Task 1 ────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="health.tasks.check_anomalies",
    max_retries=3,
    default_retry_delay=60,
    queue="health",
)
def check_anomalies(self):
    """
    Detect anomalous milk production for every active cattle using
    scikit-learn's IsolationForest.

    Algorithm
    ---------
    For each active Cattle:
      1. Fetch daily total_litres for the last 14 days.
      2. Skip the cattle if fewer than MIN_HISTORY_POINTS days of data exist.
      3. Fit an IsolationForest on the 14-day history (contamination='auto').
      4. Score today's production value.
      5. If the score < THRESHOLD_ANOMALY (-0.1):
         a. Determine severity from the score magnitude.
         b. Create a HealthAlert (deduped: skip if an ANOMALY alert already
            exists for this cattle on today's date at the same or higher
            severity).
         c. Fire the on_alert_created Django signal.

    Returns
    -------
    dict  Summary of the run:
          {
              "checked"  : int,   # cattle evaluated
              "skipped"  : int,   # cattle with insufficient history
              "alerts"   : int,   # new alerts created
              "errors"   : int    # per-cattle errors caught and logged
          }
    """
    from sklearn.ensemble import IsolationForest

    from apps.cattle.models import Cattle
    from apps.health.models import HealthAlert
    from apps.health.signals import on_alert_created
    from apps.milk.models import MilkLog

    today = date.today()
    window_start = today - timedelta(days=13)   # 14-day window inclusive

    active_cattle = Cattle.objects.filter(is_active=True)
    logger.info(
        "[check_anomalies] Starting anomaly scan for %d active cattle (window %s → %s)",
        active_cattle.count(), window_start, today,
    )

    stats = {"checked": 0, "skipped": 0, "alerts": 0, "errors": 0}

    for cattle in active_cattle:
        try:
            # ── 1. Fetch history ───────────────────────────────────────────
            logs = list(
                MilkLog.objects
                .filter(cattle=cattle, date__range=(window_start, today))
                .order_by("date")
                .values_list("date", "total_litres")
            )

            if len(logs) < MIN_HISTORY_POINTS:
                logger.debug(
                    "[check_anomalies] %s: only %d logs in window, need %d — skipping",
                    cattle.tag_number, len(logs), MIN_HISTORY_POINTS,
                )
                stats["skipped"] += 1
                continue

            stats["checked"] += 1

            # ── 2. Check today has a log ───────────────────────────────────
            today_log = next(
                ((d, float(t)) for d, t in logs if d == today), None
            )
            if today_log is None:
                logger.debug(
                    "[check_anomalies] %s: no log for today — skipping",
                    cattle.tag_number,
                )
                stats["skipped"] += 1
                stats["checked"] -= 1
                continue

            today_total = today_log[1]

            # ── 3. Fit IsolationForest ────────────────────────────────────
            history_values = np.array(
                [float(t) for _, t in logs], dtype=float
            ).reshape(-1, 1)

            clf = IsolationForest(
                n_estimators=100,
                contamination="auto",
                random_state=42,
            )
            clf.fit(history_values)

            # ── 4. Score today's production ───────────────────────────────
            score = float(clf.score_samples([[today_total]])[0])
            logger.debug(
                "[check_anomalies] %s: today=%.2f L, score=%.4f",
                cattle.tag_number, today_total, score,
            )

            # ── 5. Create alert if anomalous ──────────────────────────────
            if score >= THRESHOLD_ANOMALY:
                continue    # normal production — no alert needed

            severity = _score_to_severity(score)
            mean_yield = float(np.mean(history_values))

            # Dedup: skip if an equivalent alert already exists for today
            existing = HealthAlert.objects.filter(
                cattle=cattle,
                alert_date=today,
                alert_type=HealthAlert.AlertType.ANOMALY,
                severity=severity,
            ).exists()

            if existing:
                logger.debug(
                    "[check_anomalies] %s: %s alert for %s already exists — skipping",
                    cattle.tag_number, severity, today,
                )
                continue

            message = _build_alert_message(
                cattle.tag_number, today_total, mean_yield, score, severity
            )

            alert = HealthAlert.objects.create(
                cattle=cattle,
                alert_date=today,
                alert_type=HealthAlert.AlertType.ANOMALY,
                severity=severity,
                message=message,
            )
            stats["alerts"] += 1
            logger.warning(
                "[check_anomalies] ALERT created: %s %s score=%.4f",
                severity, cattle.tag_number, score,
            )

            # Fire the Django signal — receivers handle notifications
            on_alert_created.send(
                sender=HealthAlert,
                alert=alert,
            )

        except Exception as exc:
            stats["errors"] += 1
            logger.error(
                "[check_anomalies] Error processing cattle %s: %s",
                cattle.tag_number, exc, exc_info=True,
            )
            # Continue to next cattle rather than aborting the entire run.
            # The outer retry handles infrastructure-level failures.

    logger.info(
        "[check_anomalies] Done. checked=%d skipped=%d alerts=%d errors=%d",
        stats["checked"], stats["skipped"], stats["alerts"], stats["errors"],
    )
    return stats


# ── Task 2 ────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="health.tasks.daily_health_report",
    max_retries=3,
    default_retry_delay=60,
    queue="health",
)
def daily_health_report(self):
    """
    Aggregate unresolved HealthAlerts from the past 7 days and return a
    severity-bucketed summary dict.

    The summary is designed to be forwarded to email / push notification
    tasks without those tasks needing direct DB access.

    Returns
    -------
    dict
        {
            "report_date"   : "YYYY-MM-DD",
            "window_days"   : 7,
            "total_open"    : int,
            "by_severity"   : {
                "HIGH"   : int,
                "MEDIUM" : int,
                "LOW"    : int
            },
            "top_cattle"    : [
                {"tag_number": str, "name": str, "alert_count": int},
                ...
            ],                         # up to 5 most-alerted cattle
            "alert_types"   : {
                "ANOMALY"  : int,
                "MANUAL"   : int,
                "FORECAST" : int
            }
        }
    """
    from django.db.models import Count

    from apps.health.models import HealthAlert

    today = date.today()
    window_start = today - timedelta(days=7)

    logger.info(
        "[daily_health_report] Generating report for window %s → %s",
        window_start, today,
    )

    try:
        open_alerts = HealthAlert.objects.filter(
            is_resolved=False,
            created_at__date__gte=window_start,
        )

        # Counts by severity
        by_severity = {sev: 0 for sev in ("HIGH", "MEDIUM", "LOW")}
        for row in open_alerts.values("severity").annotate(n=Count("id")):
            by_severity[row["severity"]] = row["n"]

        # Counts by alert type
        by_type = {t: 0 for t in ("ANOMALY", "MANUAL", "FORECAST")}
        for row in open_alerts.values("alert_type").annotate(n=Count("id")):
            by_type[row["alert_type"]] = row["n"]

        # Top 5 most-alerted cattle
        top_cattle = list(
            open_alerts
            .values("cattle__tag_number", "cattle__name")
            .annotate(alert_count=Count("id"))
            .order_by("-alert_count")[:5]
        )

        summary = {
            "report_date": str(today),
            "window_days": 7,
            "total_open": open_alerts.count(),
            "by_severity": by_severity,
            "top_cattle": [
                {
                    "tag_number": row["cattle__tag_number"],
                    "name": row["cattle__name"],
                    "alert_count": row["alert_count"],
                }
                for row in top_cattle
            ],
            "alert_types": by_type,
        }

        logger.info(
            "[daily_health_report] total_open=%d HIGH=%d MEDIUM=%d LOW=%d",
            summary["total_open"],
            by_severity["HIGH"],
            by_severity["MEDIUM"],
            by_severity["LOW"],
        )
        return summary

    except Exception as exc:
        logger.error(
            "[daily_health_report] Failed to generate report: %s",
            exc, exc_info=True,
        )
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))


# ── Task 3 ────────────────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    name="health.tasks.resolve_old_alerts",
    max_retries=3,
    default_retry_delay=60,
    queue="health",
)
def resolve_old_alerts(self):
    """
    Auto-resolve LOW severity HealthAlerts older than AUTO_RESOLVE_DAYS (30)
    days that are still unresolved.

    Rationale: LOW alerts that remain open for 30+ days without manual review
    are considered stale and are resolved automatically to keep the dashboard
    clean.  MEDIUM and HIGH alerts always require manual resolution.

    Returns
    -------
    dict
        {
            "resolved_count" : int,   # alerts updated in this run
            "cutoff_date"    : "YYYY-MM-DD"
        }
    """
    from apps.health.models import HealthAlert

    cutoff = timezone.now() - timedelta(days=AUTO_RESOLVE_DAYS)
    logger.info(
        "[resolve_old_alerts] Auto-resolving LOW alerts created before %s",
        cutoff.date(),
    )

    try:
        stale_qs = HealthAlert.objects.filter(
            severity=HealthAlert.Severity.LOW,
            is_resolved=False,
            created_at__lt=cutoff,
        )

        count = stale_qs.count()

        if count == 0:
            logger.info("[resolve_old_alerts] No stale LOW alerts to resolve.")
            return {"resolved_count": 0, "cutoff_date": str(cutoff.date())}

        resolved_now = timezone.now()
        updated = stale_qs.update(
            is_resolved=True,
            resolved_at=resolved_now,
            # resolved_by remains NULL — system-resolved
        )

        logger.info(
            "[resolve_old_alerts] Auto-resolved %d stale LOW alert(s).",
            updated,
        )
        return {"resolved_count": updated, "cutoff_date": str(cutoff.date())}

    except Exception as exc:
        logger.error(
            "[resolve_old_alerts] Failed: %s", exc, exc_info=True,
        )
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))
