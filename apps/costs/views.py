from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated


class FeedLogListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Feed log list — to be implemented."})

    def post(self, request):
        return Response({"detail": "Feed log create — to be implemented."})


class ROIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "ROI calculation — to be implemented."})


class LowPerformersView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Low performers — to be implemented."})


class FarmConfigView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"detail": "Farm config GET — to be implemented."})

    def put(self, request):
        return Response({"detail": "Farm config PUT — to be implemented."})
