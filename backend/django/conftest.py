"""Shared fixtures for the Phase 1 test suite.

Fixtures are built so that each test starts from the same shape:
doctor_a/doctor_b each own a device, patient_a belongs to doctor_a only and
patient_b to doctor_b only. That makes "can A touch B's things?" expressible
as a single assertion.
"""

import os

import pytest

# config/settings.py deliberately has no fallback for these two secrets, and it
# reads them at import time - so they must exist *before* anything imports
# Django settings. The values also live in pytest.ini (env = ...); this block is
# the belt-and-braces copy so that running `pytest` with a stripped environment
# still collects. Only setdefault: a real environment always wins.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-secret")
os.environ.setdefault(
    "JWT_SIGNING_KEY", "test-only-not-a-secret-jwt-signing-key"
)
# Session creation pushes to the FastAPI registry (monitoring/telemetry.py).
# Off in tests: the suite must not depend on, or wait for, another service. The
# push is best effort in production as well - it logs and moves on.
os.environ.setdefault("TELEMETRY_SYNC_ENABLED", "False")

from rest_framework.test import APIClient  # noqa: E402

from accounts.models import (  # noqa: E402
    DoctorAssignment,
    DoctorProfile,
    PatientProfile,
    User,
)
from devices.models import Device  # noqa: E402

PASSWORD = "test12345"


def _create_user(username, role, **extra):
    return User.objects.create_user(
        username=username,
        password=PASSWORD,
        role=role,
        **extra,
    )


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def token_for(api_client):
    """Log in through the real login endpoint and return the raw access token."""

    def _token_for(user):
        response = api_client.post(
            "/api/auth/login/",
            {"username": user.username, "password": PASSWORD},
            format="json",
        )
        assert response.status_code == 200, response.content
        return response.data["access"]

    return _token_for


@pytest.fixture
def client_for(token_for):
    """An API client already authenticated as the given user."""

    def _client_for(user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {token_for(user)}")
        return client

    return _client_for


@pytest.fixture
def admin_user(db):
    return _create_user("admin_user", User.Role.ADMIN)


@pytest.fixture
def doctor_a(db):
    user = _create_user("doctor_a", User.Role.DOCTOR)
    DoctorProfile.objects.create(user=user, speciality="Cardiology")
    return user


@pytest.fixture
def doctor_b(db):
    user = _create_user("doctor_b", User.Role.DOCTOR)
    DoctorProfile.objects.create(user=user, speciality="Neurology")
    return user


@pytest.fixture
def patient_a(db, doctor_a):
    """A patient assigned to doctor_a and to nobody else."""
    user = _create_user("patient_a", User.Role.PATIENT)
    profile = PatientProfile.objects.create(user=user)
    DoctorAssignment.objects.create(doctor=doctor_a.doctor_profile, patient=profile)
    return user


@pytest.fixture
def patient_b(db, doctor_b):
    """A patient assigned to doctor_b and to nobody else."""
    user = _create_user("patient_b", User.Role.PATIENT)
    profile = PatientProfile.objects.create(user=user)
    DoctorAssignment.objects.create(doctor=doctor_b.doctor_profile, patient=profile)
    return user


@pytest.fixture
def device_a(db, doctor_a):
    return Device.objects.create(name="doctor_a device", owner=doctor_a)


@pytest.fixture
def device_b(db, doctor_b):
    return Device.objects.create(name="doctor_b device", owner=doctor_b)


@pytest.fixture
def disabled_device(db, doctor_a):
    """Owned by doctor_a, but switched off: it may not start sessions and may
    not be handed a token."""
    return Device.objects.create(
        name="doctor_a disabled device",
        owner=doctor_a,
        status=Device.Status.DISABLED,
    )
