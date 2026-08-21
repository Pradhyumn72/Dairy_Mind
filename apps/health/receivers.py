"""
Signal receivers for the health app.

on_alert_created receiver
--------------------------
Logs the new alert and serves as the extension point for downstream
notification delivery (email, push, WebSocket, etc.).

To add a notification channel, add another @receiver block below — the
signal carries the full HealthAlert instance so any receiver can act on it
without a second DB query.
"""
import logging

from django.dispatch import receiver

from .signals import on_alert_created

logger = logging.getLogger(__name__)


@receiver(on_alert_created)
def log_new_alert(sender, alert, **kwargs):
    """
    Log every new HealthAlert at the appropriate level.

    HIGH   → ERROR  (ensures visibility in error monitoring tools)
    MEDIUM → WARNING
    LOW    → INFO
    """
    from apps.health.models import HealthAlert

    level_map = {
        HealthAlert.Severity.HIGH:   logger.error,
        HealthAlert.Severity.MEDIUM: logger.warning,
        HealthAlert.Severity.LOW:    logger.info,
    }
    log_fn = level_map.get(alert.severity, logger.info)
    log_fn(
        "[on_alert_created] %s alert for %s on %s — %s",
        alert.severity,
        alert.cattle.tag_number,
        alert.alert_date,
        alert.message[:120],   # truncate for log readability
    )
