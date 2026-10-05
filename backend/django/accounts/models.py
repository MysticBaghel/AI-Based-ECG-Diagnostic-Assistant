from django.contrib.auth.models import AbstractUser, UserManager as BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models


class UserManager(BaseUserManager):
    """User manager that keeps ``role`` in step with the staff/superuser flags.

    Without this, ``manage.py createsuperuser`` produced a user whose role was
    the column default - "patient" - so the freshly created administrator could
    log into ``/admin/`` but was refused by every role-gated API endpoint. The
    role and the flags are two views of the same fact, so they are set together.

    An explicit ``role=...`` always wins, which is what the fixtures use.
    """

    def _create_user(self, username, email=None, password=None, **extra_fields):
        if "role" not in extra_fields:
            if extra_fields.get("is_superuser") or extra_fields.get("is_staff"):
                extra_fields["role"] = User.Role.ADMIN
            else:
                extra_fields["role"] = User.Role.PATIENT
        return super()._create_user(username, email, password, **extra_fields)


class User(AbstractUser):
    """Custom user model.

    Subclassing AbstractUser keeps everything Django expects from a user
    (username, password hashing, permissions, admin integration) and adds the
    single field this project needs: the user's role.
    """

    class Role(models.TextChoices):
        PATIENT = "patient", "Patient"
        DOCTOR = "doctor", "Doctor"
        ADMIN = "admin", "Admin"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.PATIENT,
    )

    objects = UserManager()

    def __str__(self):
        return self.username


class PatientProfile(models.Model):
    """Extra data for a user whose role is `patient`.

    Kept in a separate table rather than on User so doctor-only and
    patient-only fields never turn into a wide table of mostly-NULL columns.
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="patient_profile",
    )
    date_of_birth = models.DateField(null=True, blank=True)
    # blank=True and no null=True: for text, "" is the single "empty" value.
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "patient profile"
        verbose_name_plural = "patient profiles"

    def __str__(self):
        return self.user.username

    def clean(self):
        """Only enforced by full_clean() (admin/forms), not by save()."""
        if self.user_id and self.user.role != User.Role.PATIENT:
            raise ValidationError({"user": "This user's role is not 'patient'."})


class DoctorProfile(models.Model):
    """Extra data for a user whose role is `doctor`."""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="doctor_profile",
    )
    speciality = models.CharField(max_length=100, blank=True)

    # An explicit `through` model: doctor.patients.all() reads the assignment,
    # but writes must go through DoctorAssignment so created_at is recorded and
    # the (doctor, patient) uniqueness rule always applies. A through model also
    # makes .add()/.set() unavailable by design, which prevents duplicates.
    patients = models.ManyToManyField(
        PatientProfile,
        through="DoctorAssignment",
        related_name="doctors",
        blank=True,
    )

    class Meta:
        verbose_name = "doctor profile"
        verbose_name_plural = "doctor profiles"

    def __str__(self):
        return self.user.username

    def clean(self):
        """Only enforced by full_clean() (admin/forms), not by save()."""
        if self.user_id and self.user.role != User.Role.DOCTOR:
            raise ValidationError({"user": "This user's role is not 'doctor'."})


class DoctorAssignment(models.Model):
    """Which doctor is responsible for which patient."""

    doctor = models.ForeignKey(
        DoctorProfile,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    patient = models.ForeignKey(
        PatientProfile,
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["doctor", "patient"],
                name="unique_doctor_patient",
            ),
        ]

    def __str__(self):
        return f"{self.doctor} -> {self.patient}"
