"""
Root URL configuration for DairyMind.

HTML page routes (frontend)     → served by page_views.py → renders templates
REST API routes (/api/...)       → served by DRF views
Admin                            → /admin/
API docs                         → /api/docs/ (Swagger), /api/redoc/
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.accounts.page_views import (
    DashboardPageView,
    CattlePageView,
    MilkPageView,
    HealthPageView,
    ForecastPageView,
    VetReportPageView,
    CostsPageView,
    BreedingPageView,
    SettingsPageView,
)
from apps.accounts.views import login_view, logout_view, register_view

# ── REST API v1 ───────────────────────────────────────────────────────────────
api_v1_patterns = [
    path("auth/",        include("apps.accounts.urls")),
    path("cattle/",      include("apps.cattle.urls")),
    path("milk/",        include("apps.milk.urls")),
    path("alerts/",      include("apps.health.urls")),
    path("forecast/",    include("apps.forecast.urls")),
    path("vet-reports/", include("apps.vetreport.urls")),
    path("costs/",       include("apps.costs.urls")),
    path("breeding/",    include("apps.breeding.urls")),
    path("dashboard/",   include("apps.accounts.dashboard_urls")),
    path("export/",      include("apps.accounts.export_urls")),
]

urlpatterns = [
    # ── Django admin ──────────────────────────────────────────────────────────
    path("admin/", admin.site.urls),

    # ── REST API ──────────────────────────────────────────────────────────────
    path("api/", include(api_v1_patterns)),

    # ── API documentation (Swagger / ReDoc) ───────────────────────────────────
    path("api/schema/", SpectacularAPIView.as_view(),                           name="schema"),
    path("api/docs/",   SpectacularSwaggerView.as_view(url_name="schema"),      name="swagger-ui"),
    path("api/redoc/",  SpectacularRedocView.as_view(url_name="schema"),        name="redoc"),

    # ── Auth pages ────────────────────────────────────────────────────────────
    path("login/",    login_view,    name="login"),
    path("logout/",   logout_view,   name="logout"),
    path("register/", register_view, name="register"),

    # ── Frontend HTML pages ───────────────────────────────────────────────────
    path("",           DashboardPageView.as_view(), name="dashboard"),  # root → dashboard
    path("dashboard/", DashboardPageView.as_view(), name="dashboard-alt"),
    path("cattle/",    CattlePageView.as_view(),    name="cattle-page"),
    path("milk/",      MilkPageView.as_view(),      name="milk-page"),
    path("health/",    HealthPageView.as_view(),     name="health-page"),
    path("forecast/",  ForecastPageView.as_view(),   name="forecast-page"),
    path("vet-reports/", VetReportPageView.as_view(), name="vetreport-page"),
    path("costs/",     CostsPageView.as_view(),      name="costs-page"),
    path("breeding/",  BreedingPageView.as_view(),   name="breeding-page"),
    path("settings/",  SettingsPageView.as_view(),   name="settings-page"),
]

# ── Serve media files in development ─────────────────────────────────────────
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
