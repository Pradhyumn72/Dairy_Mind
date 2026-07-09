"""
Dashboard summary endpoint — aggregates KPIs from all modules.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class DashboardSummaryView(APIView):
    """
    GET /api/dashboard/summary/
    Returns KPI data for the Dashboard page.
    Full implementation in the dashboard feature task.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Placeholder — full aggregation logic implemented in the dashboard task
        return Response({"detail": "Dashboard summary endpoint — to be implemented."})
