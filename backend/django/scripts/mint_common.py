"""Shared setup for the two mint scripts.

`mint.py` reuses the device's existing active session; `mint_new.py` always
creates a new one. Everything else - the demo operator, the patient record, the
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

from accounts.models import User
from devices.models import Device
from devices.tokens import issue_device_token
from monitoring.models import Session
from monitoring.telemetry import sync_session
from patients.models import Patient


def ensure_demo_world():
    """Get (or create) the operator/patient/device the smoke tests use."""
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
    if device.owner_id != operator.id:
        device.owner = operator
        device.save(update_fields=["owner"])
    return {
        "admin": admin,
        "operator": operator,
        "patient": patient,
        "device": device,
    }


def active_session(device, patient, operator):
    """The device's current active session, creating one if there is none."""
    session = Session.objects.filter(device=device, status=Session.Status.ACTIVE).first()
    if session is None:
        session = Session.objects.create(
            patient=patient, device=device, started_by=operator
        )
    sync_session(session)
    return session


def close_active_sessions(device):
    """Mark the device's active session completed, and return its id (or None)."""
    session = Session.objects.filter(device=device, status=Session.Status.ACTIVE).first()
    if session is None:
        return None
    session.status = Session.Status.COMPLETED
    session.end_time = timezone.now()
    session.save(update_fields=["status", "end_time", "updated_at"])
    sync_session(session)
    return session.id


def new_session(device, patient, operator):
    """A brand new active session for the device, registered with FastAPI."""
    session = Session.objects.create(
        patient=patient, device=device, started_by=operator
    )
    sync_session(session)
    return session


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


def operator_token(operator) -> str:
    """A short-lived operator token for the dashboard/report proxy."""
    now = timezone.now()
    return jwt.encode(
        {
            "token_type": "access",
            "user_id": operator.id,
            "role": "operator",
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
    "operator_token",
]
