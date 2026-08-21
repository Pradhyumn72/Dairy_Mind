"""
Accounts app URL configuration.

HTML auth routes are registered at the ROOT urls.py level:
    /login/     → apps.accounts.views.login_view
    /logout/    → apps.accounts.views.logout_view
    /register/  → apps.accounts.views.register_view

This file contains only the REST API auth endpoints
served under /api/auth/...
"""
from django.urls import path
from .api_views import LoginAPIView, LogoutAPIView, CurrentUserView

urlpatterns = [
    path("login/",   LoginAPIView.as_view(),    name="api-login"),
    path("logout/",  LogoutAPIView.as_view(),   name="api-logout"),
    path("me/",      CurrentUserView.as_view(), name="api-me"),
]
