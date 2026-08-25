"""
Production Forecast URL configuration.

Route ordering matters — more specific paths must come before generic captures.

GET    /api/forecast/herd/                  HerdForecastView       ?days=30
POST   /api/forecast/refresh/               ForecastRefreshView
GET    /api/forecast/by-tag/{tag_number}/   ForecastByTagView      ?days=30
GET    /api/forecast/{cattle_id}/           CattleForecastView     ?days=30
"""
from django.urls import path
from .views import CattleForecastView, ForecastByTagView, ForecastRefreshView, HerdForecastView

urlpatterns = [
    # Named string routes first — must precede the int capture to avoid conflicts
    path("herd/",                        HerdForecastView.as_view(),    name="forecast-herd"),
    path("refresh/",                     ForecastRefreshView.as_view(), name="forecast-refresh"),
    path("by-tag/<str:tag_number>/",     ForecastByTagView.as_view(),   name="forecast-by-tag"),
    # Generic int capture last
    path("<int:cattle_id>/",             CattleForecastView.as_view(),  name="forecast-cattle"),
]
