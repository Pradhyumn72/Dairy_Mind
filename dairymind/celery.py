"""
Celery application configuration for DairyMind.
"""
import os
from celery import Celery
from django.conf import settings

# Default to development settings
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "dairymind.settings.development")

app = Celery("dairymind")

# Load Celery config from Django settings using the CELERY_ namespace
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all INSTALLED_APPS
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Utility task for checking Celery connectivity."""
    print(f"Request: {self.request!r}")
