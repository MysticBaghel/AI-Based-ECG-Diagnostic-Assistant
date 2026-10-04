from rest_framework import serializers

from .models import Device


class DeviceSerializer(serializers.ModelSerializer):
    """Owner is never taken from the request body - the view sets it to the
    authenticated caller, so one doctor cannot create a device for another."""

    class Meta:
        model = Device
        fields = ["id", "name", "owner", "status", "created_at"]
        read_only_fields = ["id", "owner", "status", "created_at"]
