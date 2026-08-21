"""
Vet Report URL configuration.

POST   /api/vet-reports/upload/     VetReportUploadView  — upload + queue task
GET    /api/vet-reports/            VetReportListView    — list, ?cattle_id=
GET    /api/vet-reports/{id}/       VetReportDetailView  — status + summary poll
"""
from django.urls import path
from .views import VetReportDetailView, VetReportListView, VetReportUploadView

urlpatterns = [
    # Upload must come before the list route so DRF doesn't treat "upload" as a PK
    path("upload/",    VetReportUploadView.as_view(),  name="vetreport-upload"),
    path("",           VetReportListView.as_view(),    name="vetreport-list"),
    path("<int:pk>/",  VetReportDetailView.as_view(),  name="vetreport-detail"),
]
