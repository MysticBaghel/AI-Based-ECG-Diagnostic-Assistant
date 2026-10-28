from rest_framework import serializers

from .models import Device


class DeviceSerializer(serializers.ModelSerializer):
    """Owner is never taken from the request body - the view sets it to the
    authenticated caller, so one doctor cannot create a device for another.

    `owner_username` is read-only and exists so the admin device list can name
    an owner without fetching every user separately.
    """

    owner_username = serializers.CharField(source="owner.username", read_only=True)

    class Meta:
        model = Device
        fields = ["id", "name", "owner", "owner_username", "status", "created_at"]
        read_only_fields = ["id", "owner", "status", "created_at"]
