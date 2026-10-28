"""Shared fixtures for the refactored ECG application.

The shape is deliberately simple: an operator who runs the clinic, an admin for
Django Admin, two permanent patient records, and a device pool. No doctor or
patient login accounts exist.
"""

import os

import pytest

# config/settings.py deliberately has no fallback for these two secrets, and it
# reads them at import time - so they must exist before anything imports Django
# settings. Only setdefault: a real environment always wins.
os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-not-a-secret")
os.environ.setdefault("JWT_SIGNING_KEY", "test-only-not-a-secret-jwt-signing-key")
# Session creation pushes to the FastAPI registry. Off in tests: the suite must
# not depend on, or wait for, another service.
os.environ.setdefault("TELEMETRY_SYNC_ENABLED", "False")

from rest_framework.test import APIClient  # noqa: E402

from accounts.models import User  # noqa: E402
from devices.models import Device  # noqa: E402
from patients.models import Patient  # noqa: E402

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
    return _create_user("admin_user", User.Role.ADMIN, is_staff=True, is_superuser=True)


@pytest.fixture
def operator(db):
    return _create_user("operator", User.Role.OPERATOR)


@pytest.fixture
def other_operator(db):
    return _create_user("other_operator", User.Role.OPERATOR)


@pytest.fixture
def patient_a(db):
    return Patient.objects.create(
        full_name="Aarav Sharma",
        phone="+91 98765 43210",
        date_of_birth="1991-02-14",
        sex=Patient.Sex.MALE,
        notes="First demo patient.",
    )


@pytest.fixture
def patient_b(db):
    return Patient.objects.create(
        full_name="Meera Iyer",
        phone="+91 90000 11122",
        date_of_birth="1984-07-03",
        sex=Patient.Sex.FEMALE,
    )


@pytest.fixture
def device_a(db, operator):
    return Device.objects.create(name="operator device", owner=operator)


@pytest.fixture
def device_b(db, operator):
    return Device.objects.create(name="shared device", owner=operator)


@pytest.fixture
def disabled_device(db, operator):
    return Device.objects.create(
        name="disabled device",
        owner=operator,
        status=Device.Status.DISABLED,
    )
