"""
Celery application configuration for DairyMind.

Worker startup
--------------
    celery -A dairymind worker -l info -Q default,health,forecast,vet

Beat scheduler startup (requires Redis or DB backend)
------------------------------------------------------
    celery -A dairymind beat -l info --scheduler django_celery_beat.schedulers:DatabaseScheduler

Queues
------
default   — general purpose
health    — health alert tasks (check_anomalies, daily_health_report, resolve_old_alerts)
forecast  — Prophet forecasting tasks
vet       — Gemini API summarization tasks
"""
import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import worker_ready

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dairymind.settings.development")

app = Celery("dairymind")

# Pull all CELERY_* settings from Django settings
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from every app in INSTALLED_APPS
app.autodiscover_tasks()

# ── Queue definitions ─────────────────────────────────────────────────────────
app.conf.task_queues = {
    "default":  {"exchange": "default",  "routing_key": "default"},
    "health":   {"exchange": "health",   "routing_key": "health"},
    "forecast": {"exchange": "forecast", "routing_key": "forecast"},
    "vet":      {"exchange": "vet",      "routing_key": "vet"},
}
app.conf.task_default_queue = "default"
app.conf.task_default_exchange = "default"
app.conf.task_default_routing_key = "default"

# ── Task routing ──────────────────────────────────────────────────────────────
app.conf.task_routes = {
    "health.tasks.*":        {"queue": "health"},
    "forecast.tasks.*":      {"queue": "forecast"},
    "vet_reports.tasks.*":   {"queue": "vet"},
}

# ── Beat schedule (fallback for environments without DB Beat) ─────────────────
# The production schedule is managed via django_celery_beat DB entries, but
# this dict acts as a human-readable reference and a fallback for testing.
app.conf.beat_schedule = {
    # Task 1 — anomaly detection every 6 hours
    "check-anomalies-every-6h": {
        "task": "health.tasks.check_anomalies",
        "schedule": crontab(minute=0, hour="*/6"),   # 00:00, 06:00, 12:00, 18:00
        "options": {"queue": "health"},
    },
    # Task 2 — daily health report at 08:00 UTC
    "daily-health-report-8am": {
        "task": "health.tasks.daily_health_report",
        "schedule": crontab(minute=0, hour=8),
        "options": {"queue": "health"},
    },
    # Task 3 — weekly stale-alert cleanup at Sunday 00:00 UTC
    "resolve-old-alerts-weekly": {
        "task": "health.tasks.resolve_old_alerts",
        "schedule": crontab(minute=0, hour=0, day_of_week="sunday"),
        "options": {"queue": "health"},
    },
    # Nightly Prophet forecast regeneration at 02:00 UTC
    "generate-all-forecasts-nightly": {
        "task": "forecast.tasks.generate_all_forecasts",
        "schedule": crontab(minute=0, hour=2),
        "options": {"queue": "forecast"},
    },
    # Breeding heat-check daily at 06:00 UTC
    "check-upcoming-heats-daily": {
        "task": "breeding.tasks.check_upcoming_heats",
        "schedule": crontab(minute=0, hour=6),
        "options": {"queue": "health"},
    },
}

# ── Worker-ready hook ─────────────────────────────────────────────────────────

@worker_ready.connect
def on_worker_ready(sender, **kwargs):
    """Log a startup message when the Celery worker is fully initialised."""
    import logging
    logging.getLogger("celery").info(
        "DairyMind Celery worker ready. Queues: default, health, forecast, vet"
    )


# ── Debug task ────────────────────────────────────────────────────────────────

@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Utility task for verifying Celery connectivity: celery -A dairymind call dairymind.celery.debug_task"""
    print(f"Request: {self.request!r}")
