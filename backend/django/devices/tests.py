"""Device registration and the device token."""

import jwt
import pytest
from django.conf import settings

pytestmark = pytest.mark.django_db


def test_patient_cannot_register_a_device(client_for, patient_a):
    response = client_for(patient_a).post(
        "/api/devices/",
        {"name": "Patient device"},
        format="json",
    )

    assert response.status_code == 403


def test_created_device_returns_a_token_for_that_device(client_for, doctor_a):
    response = client_for(doctor_a).post(
        "/api/devices/",
        {"name": "Holter 1"},
        format="json",
    )
    assert response.status_code == 201

    payload = jwt.decode(
        response.data["device_token"],
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=["HS256"],
    )

    assert payload["type"] == "device"
    assert payload["device_id"] == response.data["id"]
    assert payload["owner_id"] == doctor_a.id


def test_device_list_never_exposes_the_token(client_for, doctor_a):
    client = client_for(doctor_a)
    client.post("/api/devices/", {"name": "Holter 1"}, format="json")

    response = client.get("/api/devices/")

    assert response.status_code == 200
    assert len(response.data) == 1
    # Issued once at creation and never stored, so it cannot be read back.
    assert "device_token" not in response.data[0]


def test_doctor_lists_only_their_own_devices(client_for, doctor_a, doctor_b):
    client_for(doctor_b).post("/api/devices/", {"name": "B device"}, format="json")

    response = client_for(doctor_a).get("/api/devices/")

    assert response.status_code == 200
    assert response.data == []


def test_rotate_token_is_404_for_another_doctors_device(
    client_for, doctor_a, device_b
):
    response = client_for(doctor_a).post(
        f"/api/devices/{device_b.id}/rotate-token/"
    )

    assert response.status_code == 404


def test_owner_can_rotate_and_gets_a_fresh_token(client_for, doctor_a, device_a):
    response = client_for(doctor_a).post(
        f"/api/devices/{device_a.id}/rotate-token/"
    )

    assert response.status_code == 200
    payload = jwt.decode(
        response.data["device_token"],
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=["HS256"],
    )
    assert payload["device_id"] == str(device_a.id)


def test_admin_sees_every_device(client_for, admin_user, device_a, device_b):
    response = client_for(admin_user).get("/api/devices/")

    assert len(response.data) == 2
