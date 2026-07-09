from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class AlertListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Alert list — to be implemented."})


class AlertDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response({"detail": f"Alert {pk} — to be implemented."})


class AlertAcknowledgeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        return Response({"detail": f"Alert {pk} acknowledge — to be implemented."})
