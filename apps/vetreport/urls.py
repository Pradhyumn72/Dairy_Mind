"""
Vet Report URL configuration.

POST   /api/vet-reports/upload/                  VetReportUploadView      — upload + queue task
GET    /api/vet-reports/by-cattle/{cattle_id}/   VetReportByCattleView    — all reports for a cattle
GET    /api/vet-reports/                         VetReportListView        — list, ?cattle_id=
GET    /api/vet-reports/{id}/                    VetReportDetailView      — status + summary poll
"""
from django.urls import path
from .views import (
    VetReportByCattleView,
    VetReportDetailView,
    VetReportListView,
    VetReportUploadView,
)

urlpatterns = [
    # Specific named routes must come before the generic <int:pk>/ catch-all
    path("upload/",                          VetReportUploadView.as_view(),    name="vetreport-upload"),
    path("by-cattle/<int:cattle_id>/",       VetReportByCattleView.as_view(),  name="vetreport-by-cattle"),
    path("",                                 VetReportListView.as_view(),      name="vetreport-list"),
    path("<int:pk>/",                        VetReportDetailView.as_view(),    name="vetreport-detail"),
]
