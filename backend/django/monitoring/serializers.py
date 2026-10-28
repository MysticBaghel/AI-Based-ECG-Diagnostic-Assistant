from rest_framework import serializers

from patients.models import Patient

from .models import Session, SessionAnalysis


class SessionAnalysisSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionAnalysis
        fields = [
            "status",
            "result",
            "model_version",
            "analyzed_at",
            "error",
            "updated_at",
        ]
        read_only_fields = fields


class SessionSerializer(serializers.ModelSerializer):
    """A session as the dashboard and patient profile show it.

    ``patient_name``, ``patient_code``, ``device_name``, ``analysis_status`` and
    ``report_count`` are read-only projections so a list does not need the
    browser to join three resources. They come from the foreign keys and can
    never be spoofed by a request body.
    """

    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    patient_code = serializers.CharField(source="patient.patient_id", read_only=True)
    device_name = serializers.CharField(source="device.name", read_only=True)
    duration_seconds = serializers.FloatField(read_only=True)
    analysis = SessionAnalysisSerializer(read_only=True)
    analysis_status = serializers.SerializerMethodField()
    report_count = serializers.SerializerMethodField()
    latest_report_id = serializers.SerializerMethodField()

    class Meta:
        model = Session
        fields = [
            "id",
            "patient",
            "patient_name",
            "patient_code",
            "device",
            "device_name",
            "started_by",
            "start_time",
            "end_time",
            "duration_seconds",
            "status",
            "sample_rate_hz",
            "notes",
            "analysis",
            "analysis_status",
            "report_count",
            "latest_report_id",
        ]
        read_only_fields = [
            "id",
            "started_by",
            "start_time",
            "end_time",
            "duration_seconds",
            "status",
            "sample_rate_hz",
            "analysis",
            "analysis_status",
            "report_count",
            "latest_report_id",
        ]

    def get_analysis_status(self, obj) -> str:
        analysis = getattr(obj, "analysis", None)
        return analysis.status if analysis is not None else "not_run"

    def get_report_count(self, obj) -> int:
        annotated = getattr(obj, "report_count", None)
        if annotated is not None:
            return annotated
        return obj.reports.count()

    def get_latest_report_id(self, obj) -> str | None:
        # values_list avoids loading the PDF blob just to show its identifier.
        return (
            obj.reports.order_by("-version")
            .values_list("report_id", flat=True)
            .first()
        )

    def validate(self, attrs):
        device = attrs["device"]
        patient = attrs["patient"]

        if device.status == device.Status.DISABLED:
            raise serializers.ValidationError({"device": "This device is disabled."})

        if (
            device.assigned_patient_id is not None
            and device.assigned_patient_id != patient.id
        ):
            raise serializers.ValidationError(
                {
                    "device": (
                        "This device is dedicated to a different patient. "
                        "Unassign it first."
                    )
                }
            )

        if Session.objects.filter(
            device=device, status=Session.Status.ACTIVE
        ).exists():
            raise serializers.ValidationError(
                {"device": "This device already has an active session."}
            )

        return attrs
