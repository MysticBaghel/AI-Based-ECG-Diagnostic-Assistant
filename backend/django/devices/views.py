from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Device
from .serializers import (
    DevicePatientAssignmentSerializer,
    DeviceSerializer,
    DeviceStatusSerializer,
)
from .tokens import issue_device_token


class DeviceViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    viewsets.GenericViewSet,
):
    """Device registration, token rotation and optional patient dedication.

    All operations require an authenticated operator. There is no doctor
    ownership rule: clinic staff share the device pool, and the device may be
    dedicated to a patient so the UI can default to the right one.
    """

    serializer_class = DeviceSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Device.objects.select_related("owner", "assigned_patient")

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device = serializer.save(owner=request.user)

        data = self.get_serializer(device).data
        # The token is returned exactly once, here. It is never stored, so it
        # cannot be read back from the API - a lost token is rotated.
        data["device_token"] = issue_device_token(device)
        return Response(data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="rotate-token")
    def rotate_token(self, request, *args, **kwargs):
        """POST /api/devices/<id>/rotate-token/ - returns a fresh token."""
        device = self.get_object()

        if device.status == Device.Status.DISABLED:
            return Response(
                {"detail": "This device is disabled and cannot receive a token."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"device_token": issue_device_token(device)})

    @action(detail=True, methods=["post"], url_path="assign-patient")
    def assign_patient(self, request, *args, **kwargs):
        """POST /api/devices/<id>/assign-patient/ - dedicated or shared."""
        device = self.get_object()
        serializer = DevicePatientAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device.assigned_patient = serializer.validated_data["patient"]
        device.save(update_fields=["assigned_patient"])
        return Response(self.get_serializer(device).data)

    @action(detail=True, methods=["post"], url_path="status")
    def set_status(self, request, *args, **kwargs):
        """POST /api/devices/<id>/status/ - disable or re-enable a device."""
        device = self.get_object()
        serializer = DeviceStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        device.status = serializer.validated_data["status"]
        device.save(update_fields=["status"])
        return Response(self.get_serializer(device).data)
