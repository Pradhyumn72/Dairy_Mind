"""
Root URL configuration for DairyMind.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

api_v1_patterns = [
    path("auth/",       include("apps.accounts.urls")),
    path("cattle/",     include("apps.cattle.urls")),
    path("milk/",       include("apps.milk.urls")),
    path("alerts/",     include("apps.health.urls")),
    path("forecast/",   include("apps.forecast.urls")),
    path("vet-reports/", include("apps.vetreport.urls")),
    path("costs/",      include("apps.costs.urls")),
    path("breeding/",   include("apps.breeding.urls")),
    path("dashboard/",  include("apps.accounts.dashboard_urls")),
    path("export/",     include("apps.accounts.export_urls")),
]

urlpatterns = [
    path("admin/",   admin.site.urls),
    path("api/",     include(api_v1_patterns)),
    path("accounts/", include("apps.accounts.urls")),
    # Auto-generated API documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
