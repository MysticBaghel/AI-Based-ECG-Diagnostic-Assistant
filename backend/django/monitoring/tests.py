"""Starting and stopping sessions, and the one-active-session-per-device rule."""

import pytest
from django.db import IntegrityError, transaction

from monitoring.models import Session

pytestmark = pytest.mark.django_db


def _start(client, patient, device):
    return client.post(
        "/api/sessions/",
        {"patient": patient.patient_profile.id, "device": str(device.id)},
        format="json",
    )


def test_patient_cannot_start_a_session(client_for, patient_a, device_a):
    response = _start(client_for(patient_a), patient_a, device_a)

    assert response.status_code == 403


def test_doctor_cannot_start_a_session_for_an_unassigned_patient(
    client_for, doctor_a, patient_b, device_a
):
    response = _start(client_for(doctor_a), patient_b, device_a)

    assert response.status_code == 400
    assert "patient" in response.data


def test_doctor_cannot_use_another_doctors_device(
    client_for, doctor_a, patient_a, device_b
):
    response = _start(client_for(doctor_a), patient_a, device_b)

    assert response.status_code == 400
    assert "device" in response.data


def test_disabled_device_cannot_start_a_session(
    client_for, doctor_a, patient_a, disabled_device
):
    """A disabled device is refused at the point where it would be used."""
    response = _start(client_for(doctor_a), patient_a, disabled_device)

    assert response.status_code == 400
    assert "device" in response.data
    assert Session.objects.count() == 0


def test_doctor_can_start_and_stop_a_session(client_for, doctor_a, patient_a, device_a):
    client = client_for(doctor_a)

    started = _start(client, patient_a, device_a)
    assert started.status_code == 201
    assert started.data["status"] == "active"
    assert started.data["started_by"] == doctor_a.id
    assert started.data["end_time"] is None

    stopped = client.post(f"/api/sessions/{started.data['id']}/stop/")
    assert stopped.status_code == 200
    assert stopped.data["status"] == "completed"
    assert stopped.data["end_time"] is not None


def test_cannot_start_two_active_sessions_on_one_device(
    client_for, doctor_a, patient_a, device_a
):
    client = client_for(doctor_a)

    assert _start(client, patient_a, device_a).status_code == 201

    second = _start(client, patient_a, device_a)
    assert second.status_code == 400


def test_database_rejects_two_active_sessions(doctor_a, patient_a, device_a):
    """The rule survives even if the API check is bypassed."""
    Session.objects.create(
        patient=patient_a.patient_profile,
        device=device_a,
        started_by=doctor_a,
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Session.objects.create(
                patient=patient_a.patient_profile,
                device=device_a,
                started_by=doctor_a,
            )


def test_device_can_be_reused_once_the_session_is_stopped(
    client_for, doctor_a, patient_a, device_a
):
    """The unique index is partial (active rows only), so stopping frees it."""
    client = client_for(doctor_a)

    first = _start(client, patient_a, device_a)
    client.post(f"/api/sessions/{first.data['id']}/stop/")

    assert _start(client, patient_a, device_a).status_code == 201


def test_stopping_an_already_stopped_session_is_rejected(
    client_for, doctor_a, patient_a, device_a
):
    client = client_for(doctor_a)

    started = _start(client, patient_a, device_a)
    client.post(f"/api/sessions/{started.data['id']}/stop/")

    again = client.post(f"/api/sessions/{started.data['id']}/stop/")
    assert again.status_code == 400


def test_patient_sees_only_their_own_sessions(
    client_for, doctor_a, doctor_b, patient_a, patient_b, device_a, device_b
):
    _start(client_for(doctor_a), patient_a, device_a)
    _start(client_for(doctor_b), patient_b, device_b)

    response = client_for(patient_a).get("/api/sessions/")

    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["patient"] == patient_a.patient_profile.id


def test_doctor_sees_only_assigned_patients_sessions(
    client_for, doctor_a, doctor_b, patient_a, patient_b, device_a, device_b
):
    _start(client_for(doctor_a), patient_a, device_a)
    _start(client_for(doctor_b), patient_b, device_b)

    response = client_for(doctor_a).get("/api/sessions/")

    assert len(response.data) == 1
    assert response.data[0]["patient"] == patient_a.patient_profile.id


def test_patient_cannot_stop_a_session(client_for, doctor_a, patient_a, device_a):
    started = _start(client_for(doctor_a), patient_a, device_a)

    response = client_for(patient_a).post(
        f"/api/sessions/{started.data['id']}/stop/"
    )

    assert response.status_code == 403


def test_patient_can_read_their_own_session_detail(
    client_for, doctor_a, patient_a, device_a
):
    started = _start(client_for(doctor_a), patient_a, device_a)

    response = client_for(patient_a).get(f"/api/sessions/{started.data['id']}/")

    assert response.status_code == 200
    assert response.data["id"] == started.data["id"]
    assert response.data["patient"] == patient_a.patient_profile.id


def test_session_detail_is_404_for_someone_elses_session(
    client_for, doctor_a, doctor_b, patient_a, patient_b, device_a, device_b
):
    """Reading is scoped by the queryset, so an outsider gets 404, not 403."""
    started = _start(client_for(doctor_b), patient_b, device_b)
    url = f"/api/sessions/{started.data['id']}/"

    assert client_for(doctor_a).get(url).status_code == 404
    assert client_for(patient_a).get(url).status_code == 404


def test_session_detail_is_visible_to_the_assigned_doctor_and_to_admins(
    client_for, admin_user, doctor_a, patient_a, device_a
):
    started = _start(client_for(doctor_a), patient_a, device_a)
    url = f"/api/sessions/{started.data['id']}/"

    assert client_for(doctor_a).get(url).status_code == 200
    assert client_for(admin_user).get(url).status_code == 200
