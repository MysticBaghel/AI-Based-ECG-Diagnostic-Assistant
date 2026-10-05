"""Ingestion: readings, ECG chunks, validation, unknown sessions, heartbeats."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app import db
from app.models import ECGChunk, SensorReading
from tests.conftest import (
    DEVICE_ID,
    PATIENT_ID,
    SESSION_ID,
    bearer,
    issue_device_token,
    issue_user_token,
)


def _count(model) -> int:
    async def _run() -> int:
        async with db.SessionFactory() as session:
            return await session.scalar(select(func.count()).select_from(model))

    return asyncio.run(_run())


def _now(**offset) -> str:
    """An ISO timestamp the API accepts.

    Relative to the wall clock on purpose: an absolute literal would age into a
    422 ("timestamp is more than 300s in the future") the moment the machine
    clock passes it.
    """
    return (datetime.now(timezone.utc) + timedelta(**offset)).replace(
        microsecond=0
    ).isoformat()


def _body(session_id=SESSION_ID, **overrides) -> dict:
    body = {
        "session_id": str(session_id),
        "sensor_type": "temperature",
        "value": 36.8,
        "unit": "celsius",
    }
    body.update(overrides)
    return body


# --- scalar readings ------------------------------------------------------


def test_valid_device_token_stores_a_temperature_reading(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/data", json=_body(), headers=bearer(issue_device_token())
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stored"] is True
    assert payload["duplicate"] is False
    assert payload["sensor_type"] == "temperature"
    assert payload["value"] == 36.8
    assert payload["unit"] == "celsius"
    assert _count(SensorReading) == 1


def test_duplicate_reading_stores_one_row(scoped_client, known_session):
    device = bearer(issue_device_token())
    body = _body(recorded_at=_now())

    first = scoped_client.post("/sensor/data", json=body, headers=device)
    second = scoped_client.post("/sensor/data", json=body, headers=device)

    assert first.json()["stored"] is True
    assert second.status_code == 200
    assert second.json()["stored"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["reading_id"] == first.json()["reading_id"]
    assert _count(SensorReading) == 1


def test_unit_aliases_are_normalised(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/data",
        json=_body(sensor_type="spo2", value=98.0, unit="%"),
        headers=bearer(issue_device_token()),
    )

    assert response.status_code == 200
    assert response.json()["unit"] == "percent"


@pytest.mark.parametrize(
    "sensor_type, value, unit",
    [
        ("temperature", 60.0, "celsius"),  # above 45
        ("temperature", 10.0, "celsius"),  # below 25
        ("spo2", 20.0, "percent"),
        ("pulse", 400.0, "bpm"),
        ("motion", -5.0, "a.u."),
    ],
)
def test_out_of_range_values_are_rejected(
    scoped_client, known_session, sensor_type, value, unit
):
    response = scoped_client.post(
        "/sensor/data",
        json=_body(sensor_type=sensor_type, value=value, unit=unit),
        headers=bearer(issue_device_token()),
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"
    assert _count(SensorReading) == 0


def test_wrong_unit_for_the_sensor_type_is_rejected(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/data",
        json=_body(sensor_type="pulse", value=80.0, unit="celsius"),
        headers=bearer(issue_device_token()),
    )

    assert response.status_code == 422
    assert any("pulse" in error["message"] for error in response.json()["errors"])


def test_unknown_sensor_type_is_rejected(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/data",
        json=_body(sensor_type="glucose", value=5.0, unit="mmol"),
        headers=bearer(issue_device_token()),
    )

    assert response.status_code == 422


def test_a_timestamp_far_in_the_future_is_rejected(scoped_client, known_session):
    future = (datetime.now(timezone.utc) + timedelta(hours=3)).isoformat()

    response = scoped_client.post(
        "/sensor/data",
        json=_body(recorded_at=future),
        headers=bearer(issue_device_token()),
    )

    assert response.status_code == 422
    assert "future" in response.json()["errors"][0]["message"]


def test_a_timestamp_before_2000_is_rejected(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/data",
        json=_body(recorded_at="1999-12-31T23:59:59Z"),
        headers=bearer(issue_device_token()),
    )

    assert response.status_code == 422


def test_data_for_an_unknown_session_is_rejected(
    scoped_client, unregistered_session_id
):
    response = scoped_client.post(
        "/sensor/data",
        json=_body(session_id=unregistered_session_id),
        headers=bearer(issue_device_token()),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "unknown_session"


def test_data_from_the_wrong_device_is_rejected(scoped_client, known_session):
    """A valid device token for a device that does not own this session."""
    other = issue_device_token(uuid.UUID("22222222-2222-4222-8222-222222222222"))

    response = scoped_client.post("/sensor/data", json=_body(), headers=bearer(other))

    assert response.status_code == 403
    assert _count(SensorReading) == 0


def test_data_for_a_completed_session_is_rejected(scoped_client, known_session):
    import asyncio as _asyncio

    from app.models import KnownSession

    async def _complete() -> None:
        async with db.SessionFactory() as session:
            known = await session.get(KnownSession, known_session)
            known.status = "completed"
            await session.commit()

    _asyncio.run(_complete())

    response = scoped_client.post(
        "/sensor/data", json=_body(), headers=bearer(issue_device_token())
    )

    assert response.status_code == 409
    assert response.json()["code"] == "session_not_active"


def test_non_uuid_session_id_is_a_clean_422(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/data", json=_body(session_id="not-a-uuid"), headers=bearer(issue_device_token())
    )

    assert response.status_code == 422
    assert response.json()["code"] == "validation_error"


def test_oversized_body_is_rejected(scoped_client, known_session):
    huge = _body()
    huge["value"] = 36.8
    huge["notes"] = "x" * (1024 * 1024 + 10)

    response = scoped_client.post(
        "/sensor/data", json=huge, headers=bearer(issue_device_token())
    )

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


# --- ECG chunks -----------------------------------------------------------


def _ecg(chunk_index: int = 0, samples: int = 250) -> dict:
    return {
        "session_id": str(SESSION_ID),
        "chunk_index": chunk_index,
        "start_time": _now(),
        "sample_rate_hz": 250,
        "samples": [0.1] * samples,
    }


def test_ecg_chunk_is_stored_as_a_single_row(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/ecg", json=_ecg(), headers=bearer(issue_device_token())
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["stored"] is True
    assert payload["sample_count"] == 250
    assert payload["duration_seconds"] == 1.0
    assert _count(ECGChunk) == 1


def test_duplicate_ecg_chunk_is_idempotent(scoped_client, known_session):
    device = bearer(issue_device_token())

    first = scoped_client.post("/sensor/ecg", json=_ecg(), headers=device)
    second = scoped_client.post("/sensor/ecg", json=_ecg(), headers=device)

    assert first.json()["stored"] is True
    assert second.status_code == 200
    assert second.json()["stored"] is False
    assert second.json()["duplicate"] is True
    assert second.json()["chunk_id"] == first.json()["chunk_id"]
    assert _count(ECGChunk) == 1

    # The stored samples are the original chunk, untouched by the retry.
    async def _samples() -> list:
        async with db.SessionFactory() as session:
            chunk = await session.scalar(select(ECGChunk))
            return chunk.samples

    assert len(asyncio.run(_samples())) == 250


def test_different_chunk_indexes_are_different_rows(scoped_client, known_session):
    device = bearer(issue_device_token())

    scoped_client.post("/sensor/ecg", json=_ecg(chunk_index=0), headers=device)
    scoped_client.post("/sensor/ecg", json=_ecg(chunk_index=1), headers=device)

    assert _count(ECGChunk) == 2


def test_ecg_chunk_for_an_unknown_session_is_rejected(
    scoped_client, unregistered_session_id
):
    body = _ecg()
    body["session_id"] = str(unregistered_session_id)

    response = scoped_client.post(
        "/sensor/ecg", json=body, headers=bearer(issue_device_token())
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "overrides",
    [
        {"sample_rate_hz": 10},
        {"sample_rate_hz": 9000},
        {"samples": []},
        {"samples": [0.1] * 5001},
        {"samples": [0.1, 99.0]},
        {"chunk_index": -1},
        {"start_time": "2099-01-01T00:00:00Z"},
    ],
)
def test_invalid_ecg_chunks_are_rejected(scoped_client, known_session, overrides):
    body = _ecg()
    body.update(overrides)

    response = scoped_client.post(
        "/sensor/ecg", json=body, headers=bearer(issue_device_token())
    )

    assert response.status_code == 422
    assert _count(ECGChunk) == 0


# --- connect and heartbeat ------------------------------------------------


def test_connect_registers_the_device_as_online(scoped_client, known_session):
    response = scoped_client.post(
        "/sensor/connect",
        json={"firmware_version": "1.2.0"},
        headers=bearer(issue_device_token()),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["device_id"] == str(DEVICE_ID)
    assert payload["owner_id"] == 2
    assert payload["online"] is True
    assert payload["firmware_version"] == "1.2.0"


def test_connect_is_idempotent(scoped_client, known_session):
    device = bearer(issue_device_token())

    first = scoped_client.post("/sensor/connect", json={}, headers=device)
    second = scoped_client.post("/sensor/connect", json={}, headers=device)

    assert first.status_code == second.status_code == 200


def test_status_reports_online_then_offline_past_the_threshold(
    scoped_client, known_session
):
    """The threshold is the whole heartbeat rule: last_seen vs now."""
    from app.models import DeviceConnection

    device = bearer(issue_device_token())
    doctor = bearer(issue_user_token())

    scoped_client.post("/sensor/connect", json={}, headers=device)

    online = scoped_client.get("/sensor/status", headers=doctor).json()
    assert online["threshold_seconds"] == 120
    assert online["devices"][0]["online"] is True
    assert online["devices"][0]["seconds_since_seen"] < 120

    # Age the connection past the threshold and ask again.
    async def _age() -> None:
        async with db.SessionFactory() as session:
            connection = await session.get(DeviceConnection, DEVICE_ID)
            connection.last_seen = datetime.now(timezone.utc) - timedelta(seconds=600)
            await session.commit()

    asyncio.run(_age())

    offline = scoped_client.get("/sensor/status", headers=doctor).json()
    assert offline["devices"][0]["online"] is False
    assert offline["devices"][0]["seconds_since_seen"] > 120


def test_status_for_a_device_that_never_connected_is_offline(
    scoped_client, known_session
):
    response = scoped_client.get(
        "/sensor/status", headers=bearer(issue_user_token())
    )

    assert response.status_code == 200
    device = response.json()["devices"][0]
    assert device["device_id"] == str(DEVICE_ID)
    assert device["online"] is False
    assert device["last_seen"] is None


# --- viewer access --------------------------------------------------------


def test_readings_are_visible_to_the_patient_and_the_assigned_doctor(
    scoped_client, known_session
):
    scoped_client.post(
        "/sensor/data", json=_body(), headers=bearer(issue_device_token())
    )
    url = f"/sessions/{known_session}/readings"

    patient = scoped_client.get(url, headers=bearer(issue_user_token(PATIENT_ID, "patient")))
    doctor = scoped_client.get(url, headers=bearer(issue_user_token()))

    assert patient.status_code == 200
    assert doctor.status_code == 200
    assert patient.json()["count"] == 1
    assert patient.json()["readings"][0]["sensor_type"] == "temperature"


def test_readings_are_forbidden_for_an_unassigned_doctor_and_a_stranger(
    scoped_client, known_session
):
    url = f"/sessions/{known_session}/readings"

    other_doctor = scoped_client.get(url, headers=bearer(issue_user_token(3, "doctor")))
    stranger = scoped_client.get(url, headers=bearer(issue_user_token(99, "patient")))

    assert other_doctor.status_code == 403
    assert stranger.status_code == 403


def test_readings_are_visible_to_an_admin(scoped_client, known_session):
    response = scoped_client.get(
        f"/sessions/{known_session}/readings",
        headers=bearer(issue_user_token(1, "admin")),
    )

    assert response.status_code == 200


def test_ecg_chunk_can_be_read_back(scoped_client, known_session):
    scoped_client.post(
        "/sensor/ecg", json=_ecg(), headers=bearer(issue_device_token())
    )

    response = scoped_client.get(
        f"/sessions/{known_session}/ecg/0", headers=bearer(issue_user_token())
    )

    assert response.status_code == 200
    assert response.json()["sample_count"] == 250
    assert len(response.json()["samples"]) == 250


def test_missing_ecg_chunk_is_404(scoped_client, known_session):
    response = scoped_client.get(
        f"/sessions/{known_session}/ecg/7", headers=bearer(issue_user_token())
    )

    assert response.status_code == 404


def test_readings_for_an_unknown_session_are_404(scoped_client, unregistered_session_id):
    response = scoped_client.get(
        f"/sessions/{unregistered_session_id}/readings",
        headers=bearer(issue_user_token()),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "unknown_session"


# --- health and errors ----------------------------------------------------


def test_health_is_public(scoped_client):
    response = scoped_client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "fastapi"}


def test_internal_session_registration_is_idempotent(scoped_client):
    admin = bearer(issue_user_token(1, "admin"))
    session_id = uuid.uuid4()
    body = {
        "session_id": str(session_id),
        "patient_id": PATIENT_ID,
        "device_id": str(DEVICE_ID),
        "doctor_ids": [2],
        "status": "active",
    }

    first = scoped_client.post("/internal/sessions", json=body, headers=admin)
    second = scoped_client.post(
        "/internal/sessions", json={**body, "status": "completed"}, headers=admin
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["status"] == "completed"

    # And the registry is what the ingest path reads.
    rejected = scoped_client.post(
        "/sensor/data",
        json=_body(session_id=session_id),
        headers=bearer(issue_device_token()),
    )
    assert rejected.status_code == 409


def test_session_registration_requires_an_admin(scoped_client):
    response = scoped_client.post(
        "/internal/sessions",
        json={
            "session_id": str(uuid.uuid4()),
            "patient_id": 1,
            "device_id": str(DEVICE_ID),
        },
        headers=bearer(issue_user_token()),
    )

    assert response.status_code == 403
