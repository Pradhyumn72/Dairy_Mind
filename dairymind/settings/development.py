"""
Development settings for DairyMind.
"""
from .base import *  # noqa: F401, F403

DEBUG = True

# Allow all hosts in development
ALLOWED_HOSTS = ["*"]

# Show emails in console during development
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Django Debug Toolbar (install separately if needed)
# INSTALLED_APPS += ["debug_toolbar"]
# MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]

# Relaxed CORS in development
CORS_ALLOW_ALL_ORIGINS = True

# More verbose logging in development
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405
