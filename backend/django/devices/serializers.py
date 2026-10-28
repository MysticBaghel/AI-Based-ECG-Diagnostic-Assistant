from rest_framework import serializers

from patients.models import Patient

from .models import Device


class DeviceSerializer(serializers.ModelSerializer):
    """Owner is never taken from the request body - the view sets it to the
    authenticated caller.

    ``assigned_patient`` is read-only here; dedicating a device to a patient is
    a separate, explicit action.
    """

    owner_username = serializers.CharField(source="owner.username", read_only=True)
    assigned_patient_name = serializers.SerializerMethodField()
    assigned_patient_code = serializers.SerializerMethodField()

    class Meta:
        model = Device
        fields = [
            "id",
            "name",
            "owner",
            "owner_username",
            "status",
            "assigned_patient",
            "assigned_patient_name",
            "assigned_patient_code",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "owner",
            "assigned_patient",
            "created_at",
        ]

    def get_assigned_patient_name(self, obj) -> str | None:
        return obj.assigned_patient.full_name if obj.assigned_patient_id else None

    def get_assigned_patient_code(self, obj) -> str | None:
        return obj.assigned_patient.patient_id if obj.assigned_patient_id else None


class DevicePatientAssignmentSerializer(serializers.Serializer):
    """Body for assigning or unassigning a device.

    ``{"patient": 4}`` dedicates the device to patient 4; ``{"patient": null}``
    returns it to the shared pool.
    """

    patient = serializers.PrimaryKeyRelatedField(
        queryset=Patient.objects.all(),
        allow_null=True,
        required=True,
    )


class DeviceStatusSerializer(serializers.Serializer):
    """Body for disabling/enabling a device."""

    status = serializers.ChoiceField(choices=Device.Status.choices)
