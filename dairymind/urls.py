"""
Root URL configuration for DairyMind.
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
    CattleAddPageView,
    CattleEditPageView,
    CattleDetailPageView,
    MilkPageView,
    MilkLogPageView,
    HealthPageView,
    ForecastPageView,
    VetReportPageView,
    VetReportUploadPageView,
    CostsPageView,
    FeedLogAddPageView,
    BreedingPageView,
    HeatCycleAddPageView,
    SettingsPageView,
)
from apps.accounts.views import login_view, logout_view, register_view, profile_view

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

    # ── API docs ──────────────────────────────────────────────────────────────
    path("api/schema/", SpectacularAPIView.as_view(),                       name="schema"),
    path("api/docs/",   SpectacularSwaggerView.as_view(url_name="schema"),  name="swagger-ui"),
    path("api/redoc/",  SpectacularRedocView.as_view(url_name="schema"),    name="redoc"),

    # ── Auth ──────────────────────────────────────────────────────────────────
    path("login/",    login_view,    name="login"),
    path("logout/",   logout_view,   name="logout"),
    path("register/", register_view, name="register"),
    path("profile/",  profile_view,  name="profile-page"),

    # ── Dashboard ─────────────────────────────────────────────────────────────
    path("",           DashboardPageView.as_view(), name="dashboard"),
    path("dashboard/", DashboardPageView.as_view(), name="dashboard-alt"),

    # ── Cattle  (add/ and edit/ must come BEFORE <int:pk>/) ──────────────────
    path("cattle/",                CattlePageView.as_view(),       name="cattle-page"),
    path("cattle/add/",            CattleAddPageView.as_view(),    name="cattle-add"),
    path("cattle/<int:pk>/",       CattleDetailPageView.as_view(), name="cattle-detail"),
    path("cattle/<int:pk>/edit/",  CattleEditPageView.as_view(),   name="cattle-edit"),

    # ── Milk ──────────────────────────────────────────────────────────────────
    path("milk/",      MilkPageView.as_view(),    name="milk-page"),
    path("milk/log/",  MilkLogPageView.as_view(), name="milk-log"),

    # ── Other modules ─────────────────────────────────────────────────────────
    path("health/",               HealthPageView.as_view(),         name="health-page"),
    path("forecast/",             ForecastPageView.as_view(),       name="forecast-page"),
    path("vet-reports/",          VetReportPageView.as_view(),      name="vetreport-page"),
    path("vet-reports/upload/",   VetReportUploadPageView.as_view(),name="vetreport-upload-page"),
    path("costs/",                CostsPageView.as_view(),          name="costs-page"),
    path("costs/feed/add/",       FeedLogAddPageView.as_view(),     name="feed-add"),
    path("breeding/",                  BreedingPageView.as_view(),     name="breeding-page"),
    path("breeding/heat-cycles/add/",  HeatCycleAddPageView.as_view(), name="heat-cycle-add"),
    path("settings/",             SettingsPageView.as_view(),       name="settings-page"),
    path("profile/",              profile_view,                     name="profile-page"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
