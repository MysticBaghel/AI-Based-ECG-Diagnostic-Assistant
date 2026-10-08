"""Shared setup for the two mint scripts.

`mint.py` (Phase 2) reuses the device's existing active session; `mint_new.py`
(Phase 3) always creates a new one. Everything else - the demo users, the
device, the admin token - is identical, so it lives here and both scripts stay
short enough to read.

Nothing in here is part of a service: these are smoke-test helpers that happen
to need Django's models.

Screening aid, not a medical diagnosis.
"""

from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

from accounts.models import DoctorAssignment, DoctorProfile, PatientProfile, User
from devices.models import Device
from devices.tokens import issue_device_token
from monitoring.models import Session


def ensure_demo_world():
    """Get (or create) the admin/doctor/patient/device the smoke tests use."""
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
    return {
        "admin": admin,
        "doctor": doctor,
        "patient": patient,
        "doctor_profile": doctor_profile,
        "patient_profile": patient_profile,
        "device": device,
    }


def active_session(device, patient_profile, doctor):
    """The device's current active session, creating one if there is none."""
    session = Session.objects.filter(device=device, status=Session.Status.ACTIVE).first()
    if session is None:
        session = Session.objects.create(
            patient=patient_profile, device=device, started_by=doctor
        )
    return session


def close_active_sessions(device):
    """Mark the device's active session completed, and return its id (or None).

    Django enforces "one active session per device" with a partial unique index,
    so a *new* session cannot be created until the old one is closed - which is
    exactly the constraint a second Phase 3 run would otherwise trip over.
    """
    session = Session.objects.filter(device=device, status=Session.Status.ACTIVE).first()
    if session is None:
        return None
    session.status = Session.Status.COMPLETED
    session.end_time = timezone.now()
    session.save(update_fields=["status", "end_time"])
    return session.id


def new_session(device, patient_profile, doctor):
    """A brand new active session for the device."""
    return Session.objects.create(patient=patient_profile, device=device, started_by=doctor)


def admin_token(admin) -> str:
    """A short-lived admin access token, exactly as Django mints them."""
    now = timezone.now()
    return jwt.encode(
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


def device_token(device) -> str:
    return issue_device_token(device)


__all__ = [
    "active_session",
    "admin_token",
    "close_active_sessions",
    "device_token",
    "ensure_demo_world",
    "new_session",
]
