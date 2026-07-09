"""
CSV export endpoints for Milk_Log, Alert, and ROI_Record data.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class ExportMilkLogsView(APIView):
    """GET /api/export/milk-logs/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Milk log CSV export — to be implemented."})


class ExportAlertsView(APIView):
    """GET /api/export/alerts/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Alerts CSV export — to be implemented."})


class ExportROIView(APIView):
    """GET /api/export/roi/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "ROI CSV export — to be implemented."})
