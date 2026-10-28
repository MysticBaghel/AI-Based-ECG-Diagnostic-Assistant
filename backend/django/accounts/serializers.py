from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login serializer that puts `user_id` and `role` inside the access token.

    The claims are what let FastAPI authorise a request locally, without asking
    Django who the caller is.
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token["user_id"] = user.id
        # A legacy account may still hold "doctor"/"patient" until the data
        # migration runs; the API treats it as an operator from now on.
        token["role"] = (
            User.Role.ADMIN if user.role == User.Role.ADMIN else User.Role.OPERATOR
        )
        return token


class UserSerializer(serializers.ModelSerializer):
    """What GET /api/auth/me/ returns."""

    class Meta:
        model = User
        fields = ["id", "username", "role", "is_staff"]
        read_only_fields = fields
