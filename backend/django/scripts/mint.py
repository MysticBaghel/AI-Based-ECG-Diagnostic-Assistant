"""Smoke-test helper: mint a Django device token and register a session.

Runs inside the Django project:

    python backend/django/scripts/mint_run.py [output-file]

It prints the values a smoke test needs: DEVICE_TOKEN, SESSION_ID, USER_TOKEN,
PATIENT_ID, PATIENT_CODE and DEVICE_ID. It reuses the device's active session
when one exists.
"""

from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

from accounts.models import User
from devices.models import Device
from devices.tokens import issue_device_token
from monitoring.models import Session
from monitoring.telemetry import sync_session
from patients.models import Patient

admin, _ = User.objects.get_or_create(
    username="smoke_admin",
    defaults={"role": User.Role.ADMIN, "is_staff": True, "is_superuser": True},
)

operator, _ = User.objects.get_or_create(
    username="smoke_operator", defaults={"role": User.Role.OPERATOR}
)

patient, _ = Patient.objects.get_or_create(
    full_name="Smoke Test Patient",
    defaults={
        "phone": "+91 90000 00000",
        "sex": Patient.Sex.UNKNOWN,
        "notes": "Created by the smoke-test mint helper.",
    },
)

device, _ = Device.objects.get_or_create(
    name="smoke device", defaults={"owner": operator}
)

# Reuse the active session if one exists: a device may only have one at a time.
session = Session.objects.filter(device=device, status=Session.Status.ACTIVE).first()
if session is None:
    session = Session.objects.create(patient=patient, device=device, started_by=operator)
sync_session(session)

now = timezone.now()
user_token = jwt.encode(
    {
        "token_type": "access",
        "user_id": admin.id,
        "role": "admin",
        "iat": now,
        "exp": now + timedelta(minutes=30),
    },
    settings.SIMPLE_JWT["SIGNING_KEY"],
    algorithm=settings.SIMPLE_JWT["ALGORITHM"],
)

print("DEVICE_TOKEN=" + issue_device_token(device))
print("SESSION_ID=" + str(session.id))
print("USER_TOKEN=" + user_token)
print("PATIENT_ID=" + str(patient.id))
print("PATIENT_CODE=" + patient.patient_id)
print("DEVICE_ID=" + str(device.id))
