"""Auth: two token audiences that must not be interchangeable.

Covered here: valid device token, bad signature, expired token, wrong token
type in both directions, an `alg: none` token, a missing header, a revoked
device, and the two "this endpoint is not for that audience" cases.
"""

import uuid

import jwt
import pytest

from tests.conftest import (
    ADMIN_ID,
    DEVICE_ID,
    PATIENT_ID,
    bearer,
    issue_device_token,
    issue_user_token,
)
from app.core.config import JWT_ALGORITHM, JWT_SIGNING_KEY

READING = {
    "sensor_type": "temperature",
    "value": 36.8,
    "unit": "celsius",
}

CONNECT = {"firmware_version": "1.0.0"}


def _data_body(session_id, **overrides):
    body = {"session_id": str(session_id), **READING}
    body.update(overrides)
    return body


def test_valid_device_token_is_accepted(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/connect", json=CONNECT, headers=bearer(issue_device_token())
    )

    assert response.status_code == 200
    assert response.json()["device_id"] == str(DEVICE_ID)


def test_bad_signature_is_rejected(scoped_client, known_session):
    forged = jwt.encode(
        {"type": "device", "device_id": str(DEVICE_ID), "owner_id": 2},
        "not-the-signing-key",
        algorithm="HS256",
    )

    response = scoped_client.post(
        "/sensor/connect", json=CONNECT, headers=bearer(forged)
    )

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_expired_token_is_rejected(scoped_client, known_session):
    expired = issue_device_token(expires_in=-60)

    response = scoped_client.post(
        "/sensor/connect", json=CONNECT, headers=bearer(expired)
    )

    assert response.status_code == 401
    assert "expired" in response.json()["detail"].lower()


def test_user_token_on_a_device_endpoint_is_rejected(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/data",
        json=_data_body(known_session),
        headers=bearer(issue_user_token(PATIENT_ID, "patient")),
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Device token required."


def test_device_token_on_a_user_endpoint_is_rejected(scoped_client, known_session):
    response = scoped_client.get(
        "/sensor/status", headers=bearer(issue_device_token())
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "User access token required."


def test_refresh_token_is_not_an_access_token(scoped_client, known_session):
    refresh = issue_user_token(ADMIN_ID, "admin", token_type="refresh")

    response = scoped_client.get("/sensor/status", headers=bearer(refresh))

    assert response.status_code == 401
    assert response.json()["detail"] == "User access token required."


def test_alg_none_token_is_rejected(scoped_client, known_session):
    """`algorithms=["HS256"]` is pinned, so an unsigned token never verifies."""
    unsigned = jwt.encode(
        {
            "type": "device",
            "device_id": str(DEVICE_ID),
            "owner_id": 2,
            "exp": 4102444800,
        },
        key="",
        algorithm="none",
    )

    response = scoped_client.post(
        "/sensor/connect", json=CONNECT, headers=bearer(unsigned)
    )

    assert response.status_code == 401


def test_missing_header_is_rejected(scoped_client, known_session):
    response = scoped_client.post("/sensor/connect", json=CONNECT)

    assert response.status_code == 401
    assert "Bearer" in response.json()["detail"]


def test_device_token_without_exp_is_rejected(scoped_client, known_session):
    no_expiry = jwt.encode(
        {"type": "device", "device_id": str(DEVICE_ID), "owner_id": 2},
        JWT_SIGNING_KEY,
        algorithm=JWT_ALGORITHM,
    )

    response = scoped_client.post(
        "/sensor/connect", json=CONNECT, headers=bearer(no_expiry)
    )

    assert response.status_code == 401


def test_device_token_with_a_malformed_device_id_is_rejected(
    scoped_client, known_session
):
    broken = jwt.encode(
        {
            "type": "device",
            "device_id": "not-a-uuid",
            "owner_id": 2,
            "exp": 4102444800,
        },
        JWT_SIGNING_KEY,
        algorithm=JWT_ALGORITHM,
    )

    response = scoped_client.post(
        "/sensor/connect", json=CONNECT, headers=bearer(broken)
    )

    assert response.status_code == 401


def test_unknown_role_is_rejected(scoped_client, known_session):
    odd = issue_user_token(user_id=9, role="nurse")

    response = scoped_client.get("/sensor/status", headers=bearer(odd))

    assert response.status_code == 401


def test_revoked_device_is_refused_everywhere(scoped_client, known_session):
    """The deny list is checked on every device request."""
    admin_token = issue_user_token(ADMIN_ID, "admin")
    revoked = scoped_client.post(
        f"/internal/devices/{DEVICE_ID}/revoke",
        json={"reason": "lost"},
        headers=bearer(admin_token),
    )
    assert revoked.status_code == 200

    device_token = bearer(issue_device_token())

    assert (
        scoped_client.post("/sensor/connect", json=CONNECT, headers=device_token).status_code
        == 403
    )
    assert (
        scoped_client.post(
            "/sensor/data", json=_data_body(known_session), headers=device_token
        ).status_code
        == 403
    )
    assert (
        scoped_client.post(
            "/sensor/ecg",
            json={
                "session_id": str(known_session),
                "chunk_index": 0,
                "start_time": "2026-10-05T12:00:00Z",
                "sample_rate_hz": 250,
                "samples": [0.1, 0.2],
            },
            headers=device_token,
        ).status_code
        == 403
    )


def test_revocation_requires_an_admin_token(scoped_client, known_session):
    doctor = issue_user_token()

    response = scoped_client.post(
        f"/internal/devices/{uuid.uuid4()}/revoke",
        json={},
        headers=bearer(doctor),
    )

    assert response.status_code == 403


@pytest.mark.parametrize("role", ["patient", "doctor", "admin"])
def test_user_tokens_of_every_role_are_accepted_on_a_user_endpoint(
    scoped_client, known_session, role
):
    response = scoped_client.get(
        "/sensor/status", headers=bearer(issue_user_token(9, role))
    )

    assert response.status_code == 200
