"""
Authentication views: login, logout, user management.
"""
from django.contrib.auth import login, logout
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FarmUser
from .serializers import LoginSerializer, FarmUserSerializer


class LoginView(APIView):
    """
    POST /api/auth/login/
    Authenticates a Farm_User and returns a token.
    Returns 401 on invalid credentials (AC3).
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data, context={"request": request})
        if not serializer.is_valid():
            return Response(
                {"detail": "Invalid credentials."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        login(request, user)
        return Response(
            {
                "token": token.key,
                "user": FarmUserSerializer(user).data,
            },
            status=status.HTTP_200_OK,
        )


class LogoutView(APIView):
    """
    POST /api/auth/logout/
    Invalidates the current session token.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request):
        # Delete token to invalidate all future requests with this token
        Token.objects.filter(user=request.user).delete()
        logout(request)
        return Response({"detail": "Successfully logged out."}, status=status.HTTP_200_OK)


class CurrentUserView(APIView):
    """
    GET /api/auth/me/
    Returns the currently authenticated user's profile.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = FarmUserSerializer(request.user)
        return Response(serializer.data)
