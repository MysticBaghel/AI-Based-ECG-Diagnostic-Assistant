from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.models import User
from accounts.permissions import IsDoctorOrAdmin

from .models import Device
from .serializers import DeviceSerializer
from .tokens import issue_device_token


class DeviceViewSet(
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """GET/POST /api/devices/ and POST /api/devices/<id>/rotate-token/.

    Only list and create are exposed - Phase 1 has no use for update/delete,
    and not exposing them is safer than exposing them and relying on
    permissions alone.
    """

    serializer_class = DeviceSerializer
    # Patients are refused outright, so they never reach the queryset.
    permission_classes = [IsDoctorOrAdmin]

    def get_queryset(self):
        user = self.request.user
        queryset = Device.objects.select_related("owner")
        if user.role == User.Role.ADMIN:
            return queryset
        return queryset.filter(owner=user)

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = serializer.save(owner=request.user)

        data = self.get_serializer(device).data
        # The token is returned exactly once, here. It is never stored, so it
        # cannot be read back from the API - a lost token is rotated, not looked up.
        data["device_token"] = issue_device_token(device)
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="rotate-token")
    def rotate_token(self, request, *args, **kwargs):
        """POST /api/devices/<id>/rotate-token/ - owner or admin only.

        get_object() runs against the filtered queryset, so another doctor's
        device is a 404 rather than a 403.
        """
        device = self.get_object()
        return Response({"device_token": issue_device_token(device)})
