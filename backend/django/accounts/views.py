from rest_framework import mixins, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView

from .models import PatientProfile, User
from .serializers import (
    PatientProfileSerializer,
    RoleTokenObtainPairSerializer,
    UserSerializer,
)


class LoginView(TokenObtainPairView):
    """POST /api/auth/login/ - returns access + refresh tokens."""

    serializer_class = RoleTokenObtainPairSerializer


class MeView(APIView):
    """GET /api/auth/me/ - who the caller is, according to their token."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class PatientProfileViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """GET /api/patients/ and /api/patients/<id>/.

    Visibility is expressed once, in the queryset. Anything the caller may not
    see is simply not in the queryset, so DRF answers 404 for someone else's
    patient instead of leaking that the record exists (403 would do that).
    """

    serializer_class = PatientProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user = self.request.user
        queryset = PatientProfile.objects.select_related("user")

        if user.role == User.Role.ADMIN:
            return queryset
        if user.role == User.Role.DOCTOR:
            return queryset.filter(doctors__user=user)
        return queryset.filter(user=user)
