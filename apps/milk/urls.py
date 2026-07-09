from django.urls import path
from .views import MilkLogListCreateView, MilkLogBulkCreateView, HerdSummaryView, AnimalYieldSeriesView

urlpatterns = [
    path("logs/",                              MilkLogListCreateView.as_view(),  name="milk-log-list-create"),
    path("logs/bulk/",                         MilkLogBulkCreateView.as_view(),  name="milk-log-bulk-create"),
    path("herd-summary/",                      HerdSummaryView.as_view(),        name="milk-herd-summary"),
    path("animal/<int:animal_id>/series/",     AnimalYieldSeriesView.as_view(),  name="milk-animal-series"),
]
