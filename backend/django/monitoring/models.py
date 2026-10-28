import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Session(models.Model):
    """One ECG recording: a patient, a device and a period of time.

    UUID primary key because FastAPI stores session ids as plain UUIDs with no
    foreign keys, so both sides can reference the same session without sharing a
    database. ``patient`` points at the permanent registry row, not at a login
    account.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ABORTED = "aborted", "Aborted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    device = models.ForeignKey(
        "devices.Device",
        on_delete=models.CASCADE,
        related_name="sessions",
    )
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="started_sessions",
    )
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )
    #: Filled from the first stored ECG chunk when analysis runs. The device
    #: decides the real rate; Django records it for the report and the list.
    sample_rate_hz = models.PositiveIntegerField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-start_time"]
        constraints = [
            # "Only one active session per device", enforced by the database
            # rather than by application code: a partial unique index covering
            # active rows only, so completed sessions stay unconstrained and a
            # device can be reused.
            models.UniqueConstraint(
                fields=["device"],
                condition=Q(status="active"),
                name="unique_active_session_per_device",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.patient} on {self.device} ({self.status})"

    @property
    def duration_seconds(self) -> float | None:
        end = self.end_time or timezone.now()
        return max(0.0, (end - self.start_time).total_seconds())


class SessionAnalysis(models.Model):
    """The stored result of one analysis run for a session.

    The detailed result (measurements, quality, AI output, limitations) is kept
    as JSON because it is produced by the FastAPI compute service and must be
    preserved exactly as generated. ``status`` is duplicated as a column so the
    UI can filter without parsing JSON.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        COMPLETED = "completed", "Completed"
        UNUSABLE = "unusable", "Unusable signal"
        FAILED = "failed", "Failed"
        UNAVAILABLE = "unavailable", "Analysis unavailable"

    session = models.OneToOneField(
        Session,
        on_delete=models.CASCADE,
        related_name="analysis",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    result = models.JSONField(default=dict, blank=True)
    model_version = models.CharField(max_length=100, blank=True)
    analyzed_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "session analysis"
        verbose_name_plural = "session analyses"

    def __str__(self) -> str:
        return f"analysis of {self.session_id} ({self.status})"
