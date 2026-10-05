from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsDoctorOrAdmin

from .models import Session
from .serializers import SessionSerializer


class SessionViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Sessions are readable by whoever is involved, writable by providers."""

    serializer_class = SessionSerializer

    def get_permissions(self):
        # Patients may read their own sessions but never start or stop one.
        if self.action in ("create", "stop"):
            return [IsDoctorOrAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        user = self.request.user
        queryset = Session.objects.select_related(
            "patient__user",
            "device",
            "started_by",
        )

        if user.role == User.Role.ADMIN:
            return queryset
        if user.role == User.Role.DOCTOR:
            # Only sessions of patients this doctor is assigned to.
            return queryset.filter(patient__assignments__doctor__user=user)
        return queryset.filter(patient__user=user)

    def perform_create(self, serializer):
        serializer.save(started_by=self.request.user)

    @action(detail=True, methods=["post"])
    def stop(self, request, *args, **kwargs):
        """POST /api/sessions/<id>/stop/ - closes the session."""
        session = self.get_object()

        if session.status != Session.Status.ACTIVE:
            return Response(
                {"detail": "Session is not active."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        session.end_time = timezone.now()
        session.status = Session.Status.COMPLETED
        session.save(update_fields=["end_time", "status"])
        return Response(self.get_serializer(session).data)
