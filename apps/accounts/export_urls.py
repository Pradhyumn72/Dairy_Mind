from django.urls import path
from .export_views import ExportMilkLogsView, ExportAlertsView, ExportROIView

urlpatterns = [
    path("milk-logs/", ExportMilkLogsView.as_view(), name="export-milk-logs"),
    path("alerts/",    ExportAlertsView.as_view(),    name="export-alerts"),
    path("roi/",       ExportROIView.as_view(),       name="export-roi"),
]
