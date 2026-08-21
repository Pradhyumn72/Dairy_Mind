"""
REST API authentication views (DRF).
Served under /api/auth/...
"""
from django.contrib.auth import login, logout
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import LoginSerializer, UserSerializer as FarmUserSerializer
from .models import Profile


class LoginAPIView(APIView):
    """POST /api/auth/login/ — returns a token."""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        login(request, user)
        return Response({"token": token.key, "user": {"id": user.pk, "username": user.username}})


class LogoutAPIView(APIView):
    """POST /api/auth/logout/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        logout(request)
        return Response({"detail": "Logged out."})


class CurrentUserView(APIView):
    """GET /api/auth/me/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        u = request.user
        profile = getattr(u, 'profile', None)
        return Response({
            "id":         u.pk,
            "username":   u.username,
            "email":      u.email,
            "first_name": u.first_name,
            "last_name":  u.last_name,
            "farm_name":  profile.farm_name if profile else "",
            "role":       profile.role if profile else "",
        })
