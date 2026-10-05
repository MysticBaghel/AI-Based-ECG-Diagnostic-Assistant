"""Smoke-test helper: mint a Django device token and register a session.

This runs inside the Django project (`python manage.py shell < scripts/mint.py`
or copy/paste into `manage.py shell`). It is not part of the service.

It prints three values the smoke test needs:

* DEVICE_TOKEN - a real device JWT signed by Django
* SESSION_ID   - a UUID primary key of a real, active session
* USER_TOKEN   - an admin access token, to prove `/internal/sessions` and the
                 WebSocket accept a user token

It uses `seed_demo` data (doctor1 / patient1) when it is present, otherwise it
creates exactly what it needs.
"""

from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

from accounts.models import DoctorAssignment, DoctorProfile, PatientProfile, User
from devices.models import Device
from devices.tokens import issue_device_token
from monitoring.models import Session

admin, _ = User.objects.get_or_create(
    username="smoke_admin",
    defaults={"role": User.Role.ADMIN, "is_staff": True, "is_superuser": True},
)

doctor, _ = User.objects.get_or_create(
    username="smoke_doctor", defaults={"role": User.Role.DOCTOR}
)
doctor_profile, _ = DoctorProfile.objects.get_or_create(user=doctor)

patient, _ = User.objects.get_or_create(
    username="smoke_patient", defaults={"role": User.Role.PATIENT}
)
patient_profile, _ = PatientProfile.objects.get_or_create(user=patient)
DoctorAssignment.objects.get_or_create(doctor=doctor_profile, patient=patient_profile)

device, _ = Device.objects.get_or_create(name="smoke device", defaults={"owner": doctor})

# Reuse the active session if one exists: a device may only have one at a time.
session = Session.objects.filter(device=device, status=Session.Status.ACTIVE).first()
if session is None:
    session = Session.objects.create(
        patient=patient_profile, device=device, started_by=doctor
    )

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
print("DEVICE_ID=" + str(device.id))
