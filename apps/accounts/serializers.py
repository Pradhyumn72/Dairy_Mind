"""
Serializers for FarmUser authentication.
"""
from django.contrib.auth import authenticate
from rest_framework import serializers
from .models import FarmUser


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(write_only=True)
    password = serializers.CharField(write_only=True, style={"input_type": "password"})

    def validate(self, attrs):
        username = attrs.get("username")
        password = attrs.get("password")
        user = authenticate(
            request=self.context.get("request"),
            username=username,
            password=password,
        )
        if not user:
            # Deliberately vague to avoid field-level enumeration (Req 1, AC3)
            raise serializers.ValidationError(
                "Invalid credentials.", code="authorization"
            )
        if not user.is_active:
            raise serializers.ValidationError(
                "This account has been deactivated.", code="authorization"
            )
        attrs["user"] = user
        return attrs


class FarmUserSerializer(serializers.ModelSerializer):
    class Meta:
        model = FarmUser
        fields = ["id", "username", "email", "first_name", "last_name", "role", "is_active", "date_joined"]
        read_only_fields = ["id", "date_joined"]
