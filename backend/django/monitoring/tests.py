"""ECG sessions, analysis orchestration and the patient association."""

import pytest
from django.db import IntegrityError, transaction

from monitoring import telemetry
from monitoring.models import Session, SessionAnalysis

pytestmark = pytest.mark.django_db


def _start(client, patient, device):
    return client.post(
        "/api/sessions/",
        {"patient": patient.id, "device": str(device.id)},
        format="json",
    )


def _analysis_payload():
    return {
        "status": "completed",
        "signal": {
            "sample_rate_hz": 200,
            "sample_count": 1200,
            "duration_seconds": 6.0,
            "chunks": 3,
            "quality": {
                "score": 88.0,
                "level": "good",
                "usable": True,
                "reasons": ["No obvious quality problem detected."],
                "flatline": False,
                "clipping": False,
                "missing_samples": 0,
            },
            "filtering_note": "0.5-40 Hz + notch",
        },
        "measurements": {
            "heart_rate_bpm": 72.0,
            "rr_intervals_ms": [830.0, 835.0, 828.0],
            "rr_mean_ms": 831.0,
            "rr_std_ms": 3.2,
            "rmssd_ms": 4.1,
            "pnn50_percent": 0.0,
            "beats_detected": 4,
            "r_peak_seconds": [0.2, 1.03, 1.86, 2.69],
        },
        "ai": {
            "available": False,
            "reason": "No validated model is configured.",
            "model_name": None,
            "model_version": None,
            "classes": [],
            "predicted_class": None,
            "probabilities": None,
            "analyzed_at": None,
        },
        "limitations": ["Screening aid only."],
        "findings": ["Measured heart rate: 72 bpm."],
        "analyzed_at": "2026-10-28T10:00:00Z",
    }


def test_operator_starts_and_stops_a_session(client_for, operator, patient_a, device_a):
    client = client_for(operator)

    started = _start(client, patient_a, device_a)
    assert started.status_code == 201
    assert started.data["status"] == "active"
    assert started.data["patient"] == patient_a.id
    assert started.data["patient_code"] == patient_a.patient_id
    assert started.data["patient_name"] == patient_a.full_name
    assert started.data["started_by"] == operator.id

    stopped = client.post(f"/api/sessions/{started.data['id']}/stop/")
    assert stopped.status_code == 200
    assert stopped.data["status"] == "completed"
    assert stopped.data["end_time"] is not None


def test_a_patient_can_have_multiple_sessions(
    client_for, operator, patient_a, device_a, device_b
):
    client = client_for(operator)

    first = _start(client, patient_a, device_a)
    client.post(f"/api/sessions/{first.data['id']}/stop/")
    second = _start(client, patient_a, device_b)

    assert first.status_code == 201
    assert second.status_code == 201
    assert Session.objects.filter(patient=patient_a).count() == 2
    assert all(
        row["patient_code"] == patient_a.patient_id
        for row in client.get("/api/sessions/").data
    )


def test_second_active_session_on_one_device_is_refused(
    client_for, operator, patient_a, device_a
):
    client = client_for(operator)

    assert _start(client, patient_a, device_a).status_code == 201
    second = _start(client, patient_a, device_a)
    assert second.status_code == 400
    assert "device" in second.data


def test_database_still_enforces_one_active_session(operator, patient_a, device_a):
    Session.objects.create(patient=patient_a, device=device_a, started_by=operator)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Session.objects.create(
                patient=patient_a, device=device_a, started_by=operator
            )


def test_disabled_device_is_refused(client_for, operator, patient_a, disabled_device):
    response = _start(client_for(operator), patient_a, disabled_device)

    assert response.status_code == 400
    assert "device" in response.data


def test_device_dedicated_to_another_patient_is_refused(
    client_for, operator, patient_a, patient_b, device_a
):
    device_a.assigned_patient = patient_b
    device_a.save(update_fields=["assigned_patient"])

    response = _start(client_for(operator), patient_a, device_a)

    assert response.status_code == 400
    assert "dedicated" in response.data["device"][0]


def test_session_list_can_be_filtered_by_patient(
    client_for, operator, patient_a, patient_b, device_a, device_b
):
    client = client_for(operator)
    _start(client, patient_a, device_a)
    _start(client, patient_b, device_b)

    response = client.get(f"/api/sessions/?patient={patient_a.id}")

    assert len(response.data) == 1
    assert response.data[0]["patient"] == patient_a.id


def test_analysis_is_refused_while_the_session_is_active(
    client_for, operator, patient_a, device_a
):
    client = client_for(operator)
    started = _start(client, patient_a, device_a)

    response = client.post(f"/api/sessions/{started.data['id']}/analyze/")

    assert response.status_code == 400
    assert "Stop the recording" in response.data["detail"]


def test_analysis_runs_and_is_stored(
    client_for, operator, patient_a, device_a, monkeypatch
):
    client = client_for(operator)
    started = _start(client, patient_a, device_a)
    client.post(f"/api/sessions/{started.data['id']}/stop/")

    monkeypatch.setattr(
        telemetry, "run_analysis", lambda session_id: _analysis_payload()
    )
    response = client.post(f"/api/sessions/{started.data['id']}/analyze/")

    assert response.status_code == 200
    assert response.data["status"] == "completed"
    assert response.data["result"]["measurements"]["heart_rate_bpm"] == 72.0

    stored = SessionAnalysis.objects.get(session_id=started.data["id"])
    assert stored.status == SessionAnalysis.Status.COMPLETED
    assert stored.result["signal"]["quality"]["usable"] is True

    detail = client.get(f"/api/sessions/{started.data['id']}/analysis/")
    assert detail.status_code == 200
    assert detail.data["status"] == "completed"


def test_analysis_marks_a_telemetry_failure_instead_of_inventing_a_result(
    client_for, operator, patient_a, device_a, monkeypatch
):
    client = client_for(operator)
    started = _start(client, patient_a, device_a)
    client.post(f"/api/sessions/{started.data['id']}/stop/")

    def boom(session_id):
        raise telemetry.TelemetryError("compute service down")

    monkeypatch.setattr(telemetry, "run_analysis", boom)
    response = client.post(f"/api/sessions/{started.data['id']}/analyze/")

    assert response.status_code == 200
    assert response.data["status"] == "failed"
    assert "compute service down" in response.data["error"]
    assert response.data["result"] == {}


def test_analysis_404_before_it_runs(client_for, operator, patient_a, device_a):
    client = client_for(operator)
    started = _start(client, patient_a, device_a)
    client.post(f"/api/sessions/{started.data['id']}/stop/")

    response = client.get(f"/api/sessions/{started.data['id']}/analysis/")

    assert response.status_code == 404
