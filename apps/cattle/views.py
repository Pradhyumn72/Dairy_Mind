"""
Cattle Registry views — stub implementations.
Full logic implemented in the cattle registry feature task.
"""
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class AnimalListCreateView(APIView):
    """GET /api/cattle/   POST /api/cattle/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Animal list — to be implemented."})

    def post(self, request):
        return Response({"detail": "Animal create — to be implemented."})


class AnimalDetailView(APIView):
    """GET/PUT/DELETE /api/cattle/<pk>/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response({"detail": f"Animal {pk} detail — to be implemented."})

    def put(self, request, pk):
        return Response({"detail": f"Animal {pk} update — to be implemented."})

    def delete(self, request, pk):
        return Response({"detail": f"Animal {pk} delete — to be implemented."})


class AnimalHistoryView(APIView):
    """GET /api/cattle/<pk>/history/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        return Response({"detail": f"Animal {pk} history — to be implemented."})
