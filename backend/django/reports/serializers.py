from rest_framework import serializers

from .models import Report


class ReportSerializer(serializers.ModelSerializer):
    """Report metadata. The PDF bytes are never included in JSON."""

    session_id = serializers.UUIDField(source="session.id", read_only=True)
    patient_name = serializers.CharField(source="patient.full_name", read_only=True)
    patient_code = serializers.CharField(source="patient.patient_id", read_only=True)
    download_url = serializers.SerializerMethodField()
    analysis_status = serializers.SerializerMethodField()

    class Meta:
        model = Report
        fields = [
            "id",
            "report_id",
            "session_id",
            "patient",
            "patient_name",
            "patient_code",
            "version",
            "file_size",
            "checksum",
            "generated_at",
            "generated_by",
            "download_url",
            "analysis_status",
        ]
        read_only_fields = fields

    def get_download_url(self, obj) -> str:
        return f"/api/reports/{obj.id}/download/"

    def get_analysis_status(self, obj) -> str:
        return (obj.analysis_snapshot or {}).get("analysis_status", "unknown")
