"""Auth: token claims, /me, and who may see which patient."""

import jwt
import pytest
from django.conf import settings

from accounts.models import User

pytestmark = pytest.mark.django_db


def test_access_token_carries_user_id_and_role(token_for, doctor_a):
    payload = jwt.decode(
        token_for(doctor_a),
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=["HS256"],
    )

    assert payload["role"] == User.Role.DOCTOR
    assert payload["user_id"] == doctor_a.id


def test_me_returns_id_username_and_role(client_for, doctor_a):
    response = client_for(doctor_a).get("/api/auth/me/")

    assert response.status_code == 200
    assert response.data == {
        "id": doctor_a.id,
        "username": "doctor_a",
        "role": User.Role.DOCTOR,
    }


def test_doctor_sees_only_assigned_patients(client_for, doctor_a, patient_a, patient_b):
    response = client_for(doctor_a).get("/api/patients/")

    assert response.status_code == 200
    assert [row["username"] for row in response.data] == ["patient_a"]


def test_doctor_gets_404_for_another_doctors_patient(client_for, doctor_a, patient_b):
    response = client_for(doctor_a).get(
        f"/api/patients/{patient_b.patient_profile.id}/"
    )

    assert response.status_code == 404


def test_admin_sees_every_patient(client_for, admin_user, patient_a, patient_b):
    response = client_for(admin_user).get("/api/patients/")

    assert sorted(row["username"] for row in response.data) == [
        "patient_a",
        "patient_b",
    ]


def test_patient_sees_only_themselves(client_for, patient_a, patient_b):
    client = client_for(patient_a)

    listing = client.get("/api/patients/")
    assert [row["username"] for row in listing.data] == ["patient_a"]

    detail = client.get(f"/api/patients/{patient_b.patient_profile.id}/")
    assert detail.status_code == 404
