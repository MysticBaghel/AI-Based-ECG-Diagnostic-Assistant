"""Device registration, tokens and optional patient dedication."""

import jwt
import pytest
from django.conf import settings

from devices.models import Device

pytestmark = pytest.mark.django_db


def test_operator_registers_a_device_and_gets_a_token(client_for, operator):
    response = client_for(operator).post(
        "/api/devices/", {"name": "ESP32 · AD8232"}, format="json"
    )

    assert response.status_code == 201
    payload = jwt.decode(
        response.data["device_token"],
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=["HS256"],
    )
    assert payload["type"] == "device"
    assert payload["device_id"] == response.data["id"]
    assert payload["owner_id"] == operator.id


def test_device_list_does_not_expose_the_token(client_for, operator, device_a):
    response = client_for(operator).get("/api/devices/")

    assert response.status_code == 200
    assert [row["id"] for row in response.data] == [str(device_a.id)]
    assert "device_token" not in response.data[0]


def test_operator_can_rotate_a_token(client_for, operator, device_a):
    response = client_for(operator).post(
        f"/api/devices/{device_a.id}/rotate-token/"
    )

    assert response.status_code == 200
    assert "device_token" in response.data


def test_disabled_device_cannot_receive_a_token(client_for, operator, disabled_device):
    response = client_for(operator).post(
        f"/api/devices/{disabled_device.id}/rotate-token/"
    )

    assert response.status_code == 400


def test_device_can_be_dedicated_to_a_patient_and_unassigned(
    client_for, operator, device_a, patient_a
):
    client = client_for(operator)
    url = f"/api/devices/{device_a.id}/assign-patient/"

    assigned = client.post(url, {"patient": patient_a.id}, format="json")
    assert assigned.status_code == 200
    assert assigned.data["assigned_patient"] == patient_a.id
    assert assigned.data["assigned_patient_name"] == patient_a.full_name
    assert assigned.data["assigned_patient_code"] == patient_a.patient_id

    unassigned = client.post(url, {"patient": None}, format="json")
    assert unassigned.status_code == 200
    assert unassigned.data["assigned_patient"] is None


def test_device_status_can_be_disabled_and_reenabled(client_for, operator, device_a):
    client = client_for(operator)
    url = f"/api/devices/{device_a.id}/status/"

    disabled = client.post(url, {"status": "disabled"}, format="json")
    assert disabled.status_code == 200
    device_a.refresh_from_db()
    assert device_a.status == Device.Status.DISABLED

    enabled = client.post(url, {"status": "active"}, format="json")
    assert enabled.status_code == 200
    device_a.refresh_from_db()
    assert device_a.status == Device.Status.ACTIVE


def test_device_owner_is_the_authenticated_caller(client_for, operator):
    response = client_for(operator).post(
        "/api/devices/", {"name": "Mine", "owner": 999}, format="json"
    )

    assert response.status_code == 201
    assert response.data["owner"] == operator.id
