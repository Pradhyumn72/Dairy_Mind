"""
Milk Tracker URL configuration.

Router-generated routes (MilkLogViewSet)
-----------------------------------------
GET    /api/milk/logs/                    list
POST   /api/milk/logs/                    create
GET    /api/milk/logs/{id}/               retrieve
PUT    /api/milk/logs/{id}/               update
PATCH  /api/milk/logs/{id}/              partial_update
DELETE /api/milk/logs/{id}/              destroy

Standalone routes
-----------------
GET    /api/milk/daily-summary/           DailySummaryView    ?date=YYYY-MM-DD
GET    /api/milk/herd-summary/            HerdSummaryView     ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
GET    /api/milk/cattle/{id}/trend/       CattleTrendView     ?days=30
GET    /api/milk/top-producers/           TopProducersView    ?month=MM&year=YYYY
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CattleTrendView, DailySummaryView, HerdSummaryView, MilkLogViewSet, TopProducersView

router = DefaultRouter()
router.register(r"logs", MilkLogViewSet, basename="milk-log")

urlpatterns = [
    # ViewSet routes
    path("", include(router.urls)),

    # Standalone aggregation / analytics endpoints
    path("daily-summary/",                DailySummaryView.as_view(),  name="milk-daily-summary"),
    path("herd-summary/",                 HerdSummaryView.as_view(),   name="milk-herd-summary"),
    path("cattle/<int:cattle_id>/trend/", CattleTrendView.as_view(),   name="milk-cattle-trend"),
    path("top-producers/",                TopProducersView.as_view(),  name="milk-top-producers"),
]
