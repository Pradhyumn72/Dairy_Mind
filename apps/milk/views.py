from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class MilkLogListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Milk log list — to be implemented."})

    def post(self, request):
        return Response({"detail": "Milk log create — to be implemented."})


class MilkLogBulkCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"detail": "Milk log bulk create — to be implemented."})


class HerdSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Herd daily summary — to be implemented."})


class AnimalYieldSeriesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, animal_id):
        return Response({"detail": f"Animal {animal_id} yield series — to be implemented."})
