"""PDF report generation, versioning and authorized download."""

import pytest

from monitoring.models import Session, SessionAnalysis
from reports.models import Report
from reports.service import generate_report

pytestmark = pytest.mark.django_db


def _make_session(operator, patient, device, *, status=Session.Status.COMPLETED):
    return Session.objects.create(
        patient=patient,
        device=device,
        started_by=operator,
        status=status,
    )


def _analysis_result():
    return {
        "status": "completed",
        "signal": {
            "sample_rate_hz": 200,
            "sample_count": 800,
            "duration_seconds": 4.0,
            "chunks": 2,
            "quality": {
                "score": 82.0,
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
            "heart_rate_bpm": 68.0,
            "rr_intervals_ms": [880.0, 885.0, 882.0],
            "rr_mean_ms": 882.3,
            "rr_std_ms": 2.5,
            "rmssd_ms": 3.0,
            "pnn50_percent": 0.0,
            "beats_detected": 4,
            "r_peak_seconds": [0.2, 1.08, 1.96, 2.84],
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
        "findings": ["Measured heart rate: 68 bpm."],
        "analyzed_at": "2026-10-28T10:00:00Z",
    }


@pytest.fixture
def analysed_session(operator, patient_a, device_a):
    session = _make_session(operator, patient_a, device_a)
    SessionAnalysis.objects.create(
        session=session,
        status=SessionAnalysis.Status.COMPLETED,
        result=_analysis_result(),
        model_version="",
    )
    return session


@pytest.fixture
def ecg_payload(analysed_session):
    from reports import service

    samples = [0.1, 0.2, 0.0, -0.3, 0.8, -0.2] * 100
    original = service.telemetry.fetch_session_ecg

    def fake(session_id):
        return {
            "session_id": str(session_id),
            "sample_rate_hz": 200,
            "sample_count": len(samples),
            "chunks": [
                {
                    "chunk_index": 0,
                    "start_time": "2026-10-28T10:00:00Z",
                    "sample_rate_hz": 200,
                    "samples": samples,
                }
            ],
        }

    service.telemetry.fetch_session_ecg = fake
    yield fake
    service.telemetry.fetch_session_ecg = original


def test_report_is_a_valid_pdf_and_is_idempotent(
    client_for, operator, analysed_session, ecg_payload
):
    client = client_for(operator)
    url = f"/api/sessions/{analysed_session.id}/report/"

    first = client.post(url, {}, format="json")
    assert first.status_code == 201
    report = Report.objects.get()
    assert bytes(report.pdf).startswith(b"%PDF-1.4")
    assert bytes(report.pdf).rstrip().endswith(b"%%EOF")
    assert report.file_size > 1000
    assert len(report.checksum) == 64
    assert report.analysis_snapshot["patient"]["patient_id"] == analysed_session.patient.patient_id
    assert report.analysis_snapshot["measurements"]["heart_rate_bpm"] == 68.0

    second = client.post(url, {}, format="json")
    assert second.status_code == 200
    assert Report.objects.count() == 1
    assert second.data["report_id"] == first.data["report_id"]


def test_regenerate_creates_a_new_version(
    client_for, operator, analysed_session, ecg_payload
):
    client = client_for(operator)
    url = f"/api/sessions/{analysed_session.id}/report/"

    client.post(url, {}, format="json")
    regenerated = client.post(url, {"regenerate": True}, format="json")

    assert regenerated.status_code == 201
    assert Report.objects.count() == 2
    versions = sorted(Report.objects.values_list("version", flat=True))
    assert versions == [1, 2]

    history = client.get(f"/api/sessions/{analysed_session.id}/reports/")
    assert history.status_code == 200
    assert len(history.data) == 2


def test_report_cannot_be_generated_for_an_active_session(
    client_for, operator, patient_a, device_a
):
    active = _make_session(operator, patient_a, device_a, status=Session.Status.ACTIVE)

    response = client_for(operator).post(
        f"/api/sessions/{active.id}/report/", {}, format="json"
    )

    assert response.status_code == 400


def test_report_download_is_authorized_and_returns_a_pdf(
    client_for, operator, analysed_session, ecg_payload
):
    client = client_for(operator)
    client.post(f"/api/sessions/{analysed_session.id}/report/", {}, format="json")
    report = Report.objects.get()

    response = client.get(f"/api/reports/{report.id}/download/")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert "attachment" in response["Content-Disposition"]
    assert response.content.startswith(b"%PDF-1.4")


def test_report_download_requires_authentication(api_client, analysed_session, ecg_payload):
    report = generate_report(analysed_session, user=None)

    response = api_client.get(f"/api/reports/{report.id}/download/")

    assert response.status_code == 401


def test_report_contains_the_explicit_ai_unavailable_statement(analysed_session, ecg_payload):
    report = generate_report(analysed_session, user=None)
    # The PDF is compressed? No: the content stream is plain, so a text search is
    # meaningful here and catches a report that silently omits the disclaimer.
    body = bytes(report.pdf)
    assert b"SCREENING AID" in body
    assert b"AI classification is unavailable" in body


def test_generate_report_requires_stored_analysis(
    client_for, operator, patient_a, device_a, ecg_payload, monkeypatch
):
    session = _make_session(operator, patient_a, device_a)
    from reports import service

    from monitoring import analysis as analysis_module

    def boom(session_id):
        raise analysis_module.telemetry.TelemetryError("compute service down")

    monkeypatch.setattr(analysis_module.telemetry, "run_analysis", boom)

    response = client_for(operator).post(
        f"/api/sessions/{session.id}/report/", {}, format="json"
    )

    assert response.status_code == 400
    assert "Could not generate the report" in response.data["detail"]
