"""
Health app signals.

on_alert_created
----------------
Fired by check_anomalies (and any other code path that creates a HealthAlert)
immediately after the alert is persisted.

Receivers can connect to this signal to send notifications, push to a
WebSocket channel, trigger additional processing, etc.

Usage
-----
    from apps.health.signals import on_alert_created

    @receiver(on_alert_created)
    def handle_alert(sender, alert, **kwargs):
        ...

Signal kwargs
-------------
alert : HealthAlert instance — the newly created alert
"""
from django.dispatch import Signal

# Fired right after a new HealthAlert is saved to the database.
# sender is always the HealthAlert model class.
on_alert_created = Signal()
