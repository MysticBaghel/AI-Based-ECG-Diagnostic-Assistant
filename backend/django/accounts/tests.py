"""Authentication: JWT claims, /me, and the operator/admin model."""

import jwt
import pytest
from django.conf import settings

from accounts.models import User

pytestmark = pytest.mark.django_db


def test_access_token_carries_user_id_and_operator_role(token_for, operator):
    payload = jwt.decode(
        token_for(operator),
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=["HS256"],
    )

    assert payload["role"] == User.Role.OPERATOR
    assert payload["user_id"] == operator.id


def test_admin_token_carries_admin_role(token_for, admin_user):
    payload = jwt.decode(
        token_for(admin_user),
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithms=["HS256"],
    )

    assert payload["role"] == User.Role.ADMIN


def test_me_returns_id_username_and_role(client_for, operator):
    response = client_for(operator).get("/api/auth/me/")

    assert response.status_code == 200
    assert response.data["username"] == "operator"
    assert response.data["role"] == User.Role.OPERATOR


def test_patient_registry_requires_authentication(api_client):
    assert api_client.get("/api/patients/").status_code == 401
    assert api_client.get("/api/sessions/").status_code == 401
    assert api_client.get("/api/devices/").status_code == 401


def test_removed_doctor_endpoints_are_gone(client_for, operator):
    assert client_for(operator).get("/api/doctors/").status_code == 404
    assert client_for(operator).put("/api/patients/1/doctors/").status_code == 404
