"""
Cost Optimizer URL configuration.

POST   /api/costs/feed-log/                   FeedLogListCreateView — create feed log
GET    /api/costs/feed-log/                   FeedLogListCreateView — list feed logs
GET    /api/costs/feed-log/{id}/              FeedLogDetailView     — retrieve
PUT    /api/costs/feed-log/{id}/              FeedLogDetailView     — update
PATCH  /api/costs/feed-log/{id}/              FeedLogDetailView     — partial update
DELETE /api/costs/feed-log/{id}/              FeedLogDetailView     — delete

GET    /api/costs/summary/farm/               FarmWideSummaryView   — all cattle monthly
GET    /api/costs/summary/{cattle_id}/        CattleMonthlySummaryView — single cattle

GET    /api/costs/low-performers/             LowPerformersView     — bottom-5 by profit
GET    /api/costs/config/                     FarmConfigView        — milk price setting
PUT    /api/costs/config/                     FarmConfigView        — (documents .env approach)
"""
from django.urls import path
from .views import (
    CattleMonthlySummaryView,
    FarmConfigView,
    FarmWideSummaryView,
    FeedLogDetailView,
    FeedLogListCreateView,
    LowPerformersView,
    ROIView,
)

urlpatterns = [
    # Feed log CRUD
    path("feed-log/",          FeedLogListCreateView.as_view(), name="feed-log-list-create"),
    path("feed-log/<int:pk>/", FeedLogDetailView.as_view(),     name="feed-log-detail"),

    # Monthly summaries — "farm/" must come BEFORE "<cattle_id>/" to avoid
    # "farm" being treated as an integer PK
    path("summary/farm/",               FarmWideSummaryView.as_view(),      name="costs-farm-summary"),
    path("summary/<int:cattle_id>/",    CattleMonthlySummaryView.as_view(), name="costs-cattle-summary"),

    # Convenience / legacy routes
    path("low-performers/", LowPerformersView.as_view(), name="costs-low-performers"),
    path("roi/",            ROIView.as_view(),            name="costs-roi"),
    path("config/",         FarmConfigView.as_view(),     name="costs-config"),
]
