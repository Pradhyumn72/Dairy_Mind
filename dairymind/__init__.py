# Make Celery app available when Django starts so periodic tasks register properly.
from .celery import app as celery_app

__all__ = ("celery_app",)
