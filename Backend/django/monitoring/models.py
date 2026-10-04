import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone


class Session(models.Model):
    """One monitoring session: a patient, on a device, for a period of time.

    UUID primary key for the same reason as Device: FastAPI stores session ids
    as plain UUIDs with no foreign keys, so both sides can reference the same
    session without sharing a database.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        COMPLETED = "completed", "Completed"
        ABORTED = "aborted", "Aborted"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    patient = models.ForeignKey(
        "accounts.PatientProfile",
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
        on_delete=models.CASCADE,
        related_name="started_sessions",
    )
    start_time = models.DateTimeField(default=timezone.now)
    end_time = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
    )

    class Meta:
        ordering = ["-start_time"]
        constraints = [
            # "Only one active session per device", enforced by the database
            # rather than by application code: a partial unique index covering
            # active rows only, so completed sessions stay unconstrained and a
            # device can be reused. This also closes the race where two
            # requests pass an application-level check simultaneously.
            models.UniqueConstraint(
                fields=["device"],
                condition=Q(status="active"),
                name="unique_active_session_per_device",
            ),
        ]

    def __str__(self):
        return f"{self.patient} on {self.device} ({self.status})"
