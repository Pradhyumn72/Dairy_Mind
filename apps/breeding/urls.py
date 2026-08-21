"""
Breeding Manager URL configuration.

Router-generated routes
-----------------------
GET    /api/breeding/heat-cycles/                    list
POST   /api/breeding/heat-cycles/                    create
GET    /api/breeding/heat-cycles/{id}/               retrieve
PUT    /api/breeding/heat-cycles/{id}/               update
PATCH  /api/breeding/heat-cycles/{id}/               partial_update
DELETE /api/breeding/heat-cycles/{id}/               destroy

GET    /api/breeding/ai/{id}/                        retrieve
POST   /api/breeding/ai/{id}/mark-outcome/           mark_outcome (custom)
  ... (full CRUD)

GET    /api/breeding/pregnancy/{id}/                 retrieve
POST   /api/breeding/pregnancy/{id}/record-calving/  record_calving (custom)
  ... (full CRUD)

GET    /api/breeding/breeding-alerts/                list
GET    /api/breeding/breeding-alerts/{id}/           retrieve
POST   /api/breeding/breeding-alerts/{id}/mark-sent/ mark_sent (custom)

Standalone routes
-----------------
GET    /api/breeding/cattle/{cattle_id}/timeline/           CattleReproductiveTimelineView
GET    /api/breeding/cattle/{cattle_id}/predict-breeding/   PredictBreedingWindowView
GET    /api/breeding/cattle/{cattle_id}/ai-success-prob/    AISuccessProbabilityView
GET    /api/breeding/due-this-week/                         DueThisWeekView
GET    /api/breeding/alerts/pending/                        PendingAlertsView
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AISuccessProbabilityView,
    ArtificialInseminationViewSet,
    BreedingAlertViewSet,
    CattleReproductiveTimelineView,
    DueThisWeekView,
    HeatCycleLogViewSet,
    PendingAlertsView,
    PregnancyRecordViewSet,
    PredictBreedingWindowView,
)

router = DefaultRouter()
router.register(r"heat-cycles",      HeatCycleLogViewSet,           basename="heat-cycle")
router.register(r"ai",               ArtificialInseminationViewSet, basename="ai-event")
router.register(r"pregnancy",        PregnancyRecordViewSet,        basename="pregnancy")
router.register(r"breeding-alerts",  BreedingAlertViewSet,          basename="breeding-alert")

urlpatterns = [
    # ── ViewSet routes ────────────────────────────────────────────────────────
    path("", include(router.urls)),

    # ── Standalone analytics / convenience endpoints ──────────────────────────
    path(
        "cattle/<int:cattle_id>/timeline/",
        CattleReproductiveTimelineView.as_view(),
        name="breeding-cattle-timeline",
    ),
    path(
        "cattle/<int:cattle_id>/predict-breeding/",
        PredictBreedingWindowView.as_view(),
        name="breeding-predict-window",
    ),
    path(
        "cattle/<int:cattle_id>/ai-success-prob/",
        AISuccessProbabilityView.as_view(),
        name="breeding-ai-success-prob",
    ),
    path(
        "due-this-week/",
        DueThisWeekView.as_view(),
        name="breeding-due-this-week",
    ),
    path(
        "alerts/pending/",
        PendingAlertsView.as_view(),
        name="breeding-alerts-pending",
    ),
]
