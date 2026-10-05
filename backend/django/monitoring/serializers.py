from rest_framework import serializers

from accounts.models import DoctorAssignment, User

from .models import Session


class SessionSerializer(serializers.ModelSerializer):
    """started_by and the timestamps come from the server, never the client."""

    class Meta:
        model = Session
        fields = [
            "id",
            "patient",
            "device",
            "started_by",
            "start_time",
            "end_time",
            "status",
        ]
        read_only_fields = ["id", "started_by", "start_time", "end_time", "status"]

    def validate(self, attrs):
        """A doctor may only use their own device, for a patient they are
        assigned to. Admins are unrestricted. Patients never get this far -
        the view refuses them with 403.
        """
        user = self.context["request"].user
        patient = attrs["patient"]
        device = attrs["device"]

        if user.role == User.Role.ADMIN:
            return attrs

        if not DoctorAssignment.objects.filter(
            doctor__user=user,
            patient=patient,
        ).exists():
            raise serializers.ValidationError(
                {"patient": "You are not assigned to this patient."}
            )

        if device.owner_id != user.id:
            raise serializers.ValidationError(
                {"device": "You do not own this device."}
            )

        # Friendly message for the common case; the partial unique index on the
        # model is the guarantee that this can never be violated.
        if Session.objects.filter(device=device, status=Session.Status.ACTIVE).exists():
            raise serializers.ValidationError(
                {"device": "This device already has an active session."}
            )

        return attrs
