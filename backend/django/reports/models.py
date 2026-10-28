import uuid

from django.conf import settings
from django.db import models


def generate_report_code() -> str:
    return "RPT-" + uuid.uuid4().hex[:10].upper()


class Report(models.Model):
    """One generated PDF report, versioned per session.

    The PDF bytes are stored in the database together with the exact analysis
    snapshot used to build them. That makes a report reproducible and keeps the
    download authorized by Django rather than by a filesystem path.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    report_id = models.CharField(
        max_length=24, unique=True, editable=False, default=generate_report_code
    )
    session = models.ForeignKey(
        "monitoring.Session",
        on_delete=models.CASCADE,
        related_name="reports",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="reports",
    )
    version = models.PositiveIntegerField(default=1)
    analysis_snapshot = models.JSONField(default=dict, blank=True)
    pdf = models.BinaryField()
    file_size = models.PositiveIntegerField(default=0)
    checksum = models.CharField(max_length=64, blank=True)
    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="generated_reports",
    )

    class Meta:
        ordering = ["-generated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "version"],
                name="unique_report_version_per_session",
            )
        ]
        indexes = [models.Index(fields=["patient", "generated_at"])]

    def __str__(self) -> str:
        return f"{self.report_id} (session {self.session_id}, v{self.version})"
