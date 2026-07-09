from django.urls import path
from .views import HerdForecastView, AnimalForecastView, ForecastRefreshView

urlpatterns = [
    path("herd/",                          HerdForecastView.as_view(),     name="forecast-herd"),
    path("animal/<int:animal_id>/",        AnimalForecastView.as_view(),   name="forecast-animal"),
    path("refresh/",                       ForecastRefreshView.as_view(),  name="forecast-refresh"),
]
