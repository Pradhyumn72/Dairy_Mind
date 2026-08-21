"""
Cattle Registry URL configuration.

Router-generated routes
-----------------------
GET    /api/cattle/                          list
POST   /api/cattle/                          create
GET    /api/cattle/{id}/                     retrieve
PUT    /api/cattle/{id}/                     update
PATCH  /api/cattle/{id}/                     partial_update
DELETE /api/cattle/{id}/                     destroy

Custom action routes
--------------------
GET    /api/cattle/{id}/milk-history/        milk_history
GET    /api/cattle/{id}/health-timeline/     health_timeline
GET    /api/cattle/{id}/dashboard/           dashboard
POST   /api/cattle/{id}/deactivate/          deactivate
GET    /api/cattle/{id}/history/             history
"""
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CattleViewSet

router = DefaultRouter()
router.register(r"", CattleViewSet, basename="cattle")

urlpatterns = [
    path("", include(router.urls)),
]
