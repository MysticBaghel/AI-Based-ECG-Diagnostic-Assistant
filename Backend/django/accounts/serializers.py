from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import PatientProfile, User


class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login serializer that puts `user_id` and `role` inside the access token.

    The claims are what let FastAPI authorise a request locally, without asking
    Django who the caller is.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["user_id"] = user.id
        token["role"] = user.role
        return token


class UserSerializer(serializers.ModelSerializer):
    """What GET /api/auth/me/ returns."""

    class Meta:
        model = User
        fields = ["id", "username", "role"]
        read_only_fields = fields


class PatientProfileSerializer(serializers.ModelSerializer):
    """Read-only view of a patient, for the patient list endpoints."""

    username = serializers.CharField(source="user.username", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = PatientProfile
        fields = ["id", "user", "username", "email", "date_of_birth", "notes"]
        read_only_fields = fields
