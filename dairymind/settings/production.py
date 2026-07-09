"""
Production settings for DairyMind.
"""
from decouple import config
from .base import *  # noqa: F401, F403

DEBUG = False

# Security hardening
SECURE_HSTS_SECONDS = 31536000  # 1 year
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Enforce strict CORS in production
CORS_ALLOW_ALL_ORIGINS = False
