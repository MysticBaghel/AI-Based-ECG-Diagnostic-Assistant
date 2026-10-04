"""Create a small, repeatable demo dataset.

    python manage.py seed_demo

Idempotent: running it again reuses the same usernames, resets their
passwords to the demo password and re-creates any missing profile or
assignment, so it is safe to run after a partial failure.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import DoctorAssignment, DoctorProfile, PatientProfile, User

DEMO_PASSWORD = "demo12345"

ADMIN_USERNAME = "admin"

# (doctor username, speciality, patients assigned to that doctor)
DOCTORS = [
    ("doctor1", "Cardiology", ["patient1", "patient2"]),
    ("doctor2", "Neurology", ["patient3", "patient4"]),
]


class Command(BaseCommand):
    help = "Seed 1 admin, 2 doctors and 4 patients (password: demo12345)."

    @transaction.atomic
    def handle(self, *args, **options):
        seeded = [
            self._upsert_user(
                ADMIN_USERNAME,
                User.Role.ADMIN,
                is_staff=True,
                is_superuser=True,
            )
        ]

        for doctor_username, speciality, patient_usernames in DOCTORS:
            doctor_user = self._upsert_user(doctor_username, User.Role.DOCTOR)
            doctor_profile, _ = DoctorProfile.objects.get_or_create(
                user=doctor_user,
                defaults={"speciality": speciality},
            )
            seeded.append(doctor_user)

            for patient_username in patient_usernames:
                patient_user = self._upsert_user(patient_username, User.Role.PATIENT)
                patient_profile, _ = PatientProfile.objects.get_or_create(
                    user=patient_user
                )
                DoctorAssignment.objects.get_or_create(
                    doctor=doctor_profile,
                    patient=patient_profile,
                )
                seeded.append(patient_user)

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(seeded)} users (password: {DEMO_PASSWORD})"
            )
        )
        for user in seeded:
            self.stdout.write(f"  {user.username:<10} {user.role}")

    def _upsert_user(self, username, role, **extra):
        user, _ = User.objects.get_or_create(username=username)
        user.role = role
        for field, value in extra.items():
            setattr(user, field, value)
        # Always reset, so the demo password is guaranteed to work.
        user.set_password(DEMO_PASSWORD)
        user.save()
        return user
