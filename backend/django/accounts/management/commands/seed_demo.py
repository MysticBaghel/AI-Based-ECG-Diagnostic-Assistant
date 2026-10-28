"""Create a small, repeatable demo dataset.

    python manage.py seed_demo

Idempotent: running it again reuses the same usernames, resets their passwords
to the demo password and re-creates any missing patient or device, so it is safe
to run after a partial failure.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from devices.models import Device
from patients.models import Patient

DEMO_PASSWORD = "demo12345"

ADMIN_USERNAME = "admin"
OPERATOR_USERNAME = "operator"

DEMO_PATIENTS = [
    ("Aarav Sharma", "+91 98765 43210", "1991-02-14", "male"),
    ("Meera Iyer", "+91 90000 11122", "1984-07-03", "female"),
    ("Rohan Das", "+91 90000 33344", None, "male"),
]


class Command(BaseCommand):
    help = (
        "Seed 1 admin, 1 operator, 3 patients and a simulator device "
        "(password: demo12345)."
    )

    @transaction.atomic
    def handle(self, *args, **options):
        seeded = [
            self._upsert_user(
                ADMIN_USERNAME,
                User.Role.ADMIN,
                is_staff=True,
                is_superuser=True,
            ),
            self._upsert_user(OPERATOR_USERNAME, User.Role.OPERATOR),
        ]

        for full_name, phone, date_of_birth, sex in DEMO_PATIENTS:
            patient, created = Patient.objects.get_or_create(
                full_name=full_name,
                defaults={
                    "phone": phone,
                    "date_of_birth": date_of_birth,
                    "sex": sex,
                    "notes": "Demo patient created by seed_demo.",
                },
            )
            if created:
                self.stdout.write(f"  patient {patient.patient_id} {patient.full_name}")

        operator = seeded[1]
        Device.objects.get_or_create(
            name="ESP32 · AD8232 simulator",
            defaults={"owner": operator},
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {len(seeded)} users and {len(DEMO_PATIENTS)} demo patients "
                f"(password: {DEMO_PASSWORD})"
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
