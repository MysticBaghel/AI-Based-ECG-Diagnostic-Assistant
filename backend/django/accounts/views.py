from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .serializers import RoleTokenObtainPairSerializer, UserSerializer


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ - returns access + refresh tokens."""

    serializer_class = RoleTokenObtainPairSerializer


class MeView(APIView):
    """GET /api/auth/me/ - who the caller is, according to their token."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)
