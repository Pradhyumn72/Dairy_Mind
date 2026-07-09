from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class HerdForecastView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Herd forecast — to be implemented."})


class AnimalForecastView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, animal_id):
        return Response({"detail": f"Animal {animal_id} forecast — to be implemented."})


class ForecastRefreshView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        return Response({"detail": "Forecast refresh — to be implemented."})
