"""
Production Forecast URL configuration.

GET    /api/forecast/herd/                  HerdForecastView        ?days=30
GET    /api/forecast/{cattle_id}/           CattleForecastView      ?days=30&history=90&refresh=false
POST   /api/forecast/refresh/               ForecastRefreshView     (enqueue background task)
"""
from django.urls import path
from .views import CattleForecastView, ForecastRefreshView, HerdForecastView

urlpatterns = [
    # Herd-level aggregate forecast
    path("herd/",                    HerdForecastView.as_view(),    name="forecast-herd"),
    # Per-cattle forecast — must come AFTER herd/ so "herd" isn't matched as cattle_id
    path("<int:cattle_id>/",         CattleForecastView.as_view(),  name="forecast-cattle"),
    # Manual refresh trigger
    path("refresh/",                 ForecastRefreshView.as_view(), name="forecast-refresh"),
]
