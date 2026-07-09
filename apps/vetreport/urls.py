from django.urls import path
from .views import VetReportListView, VetReportUploadView, VetReportDetailView

urlpatterns = [
    path("",         VetReportListView.as_view(),   name="vetreport-list"),
    path("upload/",  VetReportUploadView.as_view(),  name="vetreport-upload"),
    path("<int:pk>/", VetReportDetailView.as_view(), name="vetreport-detail"),
]
