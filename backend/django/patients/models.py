"""The patient registry.

A patient is a permanent record owned by the clinic, not a login account. The
operator registers a patient once and every ECG session points at this row, so
a returning patient is found by name, phone number or the generated patient ID
instead of creating a duplicate record.

``id`` is the internal integer primary key (and the value ECG sessions store).
``patient_id`` is the application-generated public identifier printed on reports
and spoken over the phone. The phone number is deliberately *not* a key: it is
optional, can be shared, and can change.
"""

import secrets

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


def generate_patient_id() -> str:
    """A short, permanent, human-readable ID such as ``PT-7F3A9C21``.

    Random rather than sequential so that an ID does not disclose how many
    patients the clinic has. ``secrets`` is used instead of ``random`` because
    the value is exposed outside the database.
    """
    return "PT-" + secrets.token_hex(4).upper()


class Patient(models.Model):
    class Sex(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        FEMALE = "female", "Female"
        MALE = "male", "Male"
        OTHER = "other", "Other"

    patient_id = models.CharField(
        max_length=20,
        unique=True,
        editable=False,
        default=generate_patient_id,
        help_text="Permanent application-generated patient identifier.",
    )
    full_name = models.CharField(max_length=200)
    phone = models.CharField(max_length=32, blank=True, db_index=True)
    #: Digits only. Used for duplicate detection so "+91 98765 43210" and
    #: "9876543210" are recognised as the same number; never used as a key.
    phone_normalized = models.CharField(max_length=32, blank=True, db_index=True)
    email = models.EmailField(blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    age_years = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(130)],
        help_text="Only needed when the date of birth is unknown.",
    )
    sex = models.CharField(max_length=20, choices=Sex.choices, default=Sex.UNKNOWN)
    notes = models.TextField(blank=True)
    #: Link back to a pre-refactor patient login account. New registrations do
    #: not create one; the column exists so the migration preserves the mapping.
    legacy_user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="legacy_patient",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "id"]
        indexes = [
            models.Index(fields=["full_name"]),
        ]

    def __str__(self) -> str:
        return f"{self.full_name} ({self.patient_id})"

    @property
    def age(self) -> int | None:
        """Whole years, from the date of birth when known."""
        if self.date_of_birth is None:
            return self.age_years
        dob = self.date_of_birth
        if isinstance(dob, str):
            from datetime import date

            try:
                dob = date.fromisoformat(dob[:10])
            except ValueError:
                return self.age_years
        today = timezone.localdate()
        years = today.year - dob.year
        if (today.month, today.day) < (dob.month, dob.day):
            years -= 1
        return max(0, years)

    def save(self, *args, **kwargs):
        # Keep the normalised copy in step with whatever was typed. Imported
        # lazily so this module stays free of serializer imports.
        from .normalisation import normalise_phone

        self.phone = (self.phone or "").strip()
        self.phone_normalized = normalise_phone(self.phone)
        if self.patient_id:
            self.patient_id = self.patient_id.strip().upper()
        super().save(*args, **kwargs)
