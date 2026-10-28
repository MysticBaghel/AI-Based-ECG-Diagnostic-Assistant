"""Report generation from stored data - no fabricated values."""

from __future__ import annotations

import hashlib
import logging
from datetime import timezone as dt_timezone

from django.db import transaction
from django.utils import timezone

from monitoring import telemetry
from monitoring.analysis import run_and_store
from monitoring.models import Session

from .models import Report
from .pdf import render_report

logger = logging.getLogger(__name__)

DISCLAIMER = (
    "Screening aid, not a standalone medical diagnosis. A qualified clinician "
    "must interpret this recording in the clinical context."
)

BASE_LIMITATIONS = [
    "Single-lead ECG; rhythm and morphology assessment is limited compared with a clinical ECG.",
    "Signal processing can fail on noisy, clipped, flat or very short recordings; measurements are withheld when quality is insufficient.",
    "The AI component, when available, is an experimental classifier. Its output is not a diagnosis and has not been validated for clinical use in this deployment.",
    "This report does not replace review by a qualified clinician.",
]


def _iso(value) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    if timezone.is_naive(value):
        value = timezone.make_aware(value, dt_timezone.utc)
    return value.astimezone(dt_timezone.utc).isoformat()


def _decimate(samples: list[float], limit: int = 4000) -> list[float]:
    """Bound the stored snapshot so a long recording does not bloat the row."""
    if len(samples) <= limit:
        return samples
    stride = len(samples) / limit
    return [samples[min(len(samples) - 1, int(index * stride))] for index in range(limit)]


def _waveform(session: Session) -> tuple[list[float], int | None, float]:
    try:
        payload = telemetry.fetch_session_ecg(str(session.id))
    except telemetry.TelemetryError as exc:
        logger.warning("Could not load ECG samples for report %s: %s", session.id, exc)
        return [], session.sample_rate_hz, 0.0

    chunks = sorted(payload.get("chunks") or [], key=lambda item: item.get("chunk_index", 0))
    samples: list[float] = []
    rate = payload.get("sample_rate_hz") or session.sample_rate_hz
    for chunk in chunks:
        chunk_samples = chunk.get("samples") or []
        chunk_rate = chunk.get("sample_rate_hz")
        if chunk_rate and not rate:
            rate = chunk_rate
        # A different rate mid-recording is not silently resampled; the DSP has
        # already flagged the inconsistency, and the PDF should not pretend.
        if chunk_rate and rate and chunk_rate != rate:
            continue
        samples.extend(float(value) for value in chunk_samples)
    duration = len(samples) / rate if rate else 0.0
    return _decimate(samples), rate, duration


def _findings(analysis_payload: dict) -> list[str]:
    findings: list[str] = []
    quality = ((analysis_payload.get("signal") or {}).get("quality") or {})
    measurements = analysis_payload.get("measurements") or {}

    if quality.get("usable") is False:
        findings.append(
            "The signal did not meet the quality threshold, so rhythm measurements "
            "are not reported from this recording."
        )
    elif measurements.get("heart_rate_bpm") is not None:
        findings.append(
            f"Signal processing measured a heart rate of about "
            f"{float(measurements['heart_rate_bpm']):.0f} bpm from "
            f"{measurements.get('beats_detected', 0)} detected beats."
        )
        findings.append(
            "Heart rate and RR intervals are descriptive measurements. They are not "
            "an interpretation of rhythm or a diagnosis."
        )

    ai = analysis_payload.get("ai") or {}
    if ai.get("available") and ai.get("predicted_class"):
        probability = (ai.get("probabilities") or {}).get(ai.get("predicted_class"))
        suffix = f" (model probability {float(probability) * 100:.1f}%)" if probability is not None else ""
        findings.append(
            f"The experimental classifier suggested '{ai['predicted_class']}'{suffix}. "
            "This is a screening signal, not a diagnosis."
        )
    elif not ai.get("available"):
        findings.append(
            "No validated AI classification model is available, so no AI finding is reported."
        )

    if not findings:
        findings.append("No validated measurement or AI finding is available for this recording.")
    return findings


def _payload(session: Session, report: Report | None, version: int) -> dict:
    analysis = getattr(session, "analysis", None)
    snapshot = analysis.result if analysis is not None else {}

    if analysis is None:
        raise ValueError("Run the analysis before generating a report.")

    ai = snapshot.get("ai") or {}
    signal = snapshot.get("signal") or {}
    measurements = snapshot.get("measurements") or {}
    samples, rate, duration = _waveform(session)

    # Prefer the compute service's limitations (which already cover the
    # single-lead and validation caveats) over duplicating them with the local
    # fallback list.
    limitations = list(snapshot.get("limitations") or BASE_LIMITATIONS)

    return {
        "application": "AI-Based ECG Diagnostic Assistant",
        "report_id": report.report_id if report is not None else "PENDING",
        "version": version,
        "generated_at": _iso(timezone.now()),
        "analysis_status": analysis.status,
        "patient": {
            "full_name": session.patient.full_name,
            "patient_id": session.patient.patient_id,
            "phone": session.patient.phone,
            "date_of_birth": (
                session.patient.date_of_birth.isoformat()
                if hasattr(session.patient.date_of_birth, "isoformat")
                else (str(session.patient.date_of_birth) if session.patient.date_of_birth else None)
            ),
            "age": session.patient.age,
            "sex": session.patient.sex,
        },
        "session": {
            "id": str(session.id),
            "device_name": session.device.name,
            "start_time": _iso(session.start_time),
            "end_time": _iso(session.end_time),
            "duration_seconds": session.duration_seconds,
            "sample_rate_hz": rate or session.sample_rate_hz,
        },
        "signal": {
            **signal,
            "sample_rate_hz": rate or signal.get("sample_rate_hz"),
            "duration_seconds": duration or signal.get("duration_seconds"),
        },
        "measurements": measurements,
        "ai": ai,
        "findings": _findings(snapshot),
        "limitations": limitations,
        "waveform_samples": samples,
        "disclaimer": DISCLAIMER,
    }


@transaction.atomic
def generate_report(session: Session, *, user=None, regenerate: bool = False) -> Report:
    """Generate or return the latest report for a completed session.

    Without ``regenerate`` this is idempotent: an existing report is returned
    instead of creating a duplicate. With ``regenerate`` a new version is
    created from the current stored analysis.
    """
    if session.status == Session.Status.ACTIVE:
        raise ValueError("Stop the recording before generating a report.")

    existing = session.reports.order_by("-version").first()
    if existing is not None and not regenerate:
        return existing

    analysis = getattr(session, "analysis", None)
    if analysis is None or analysis.status == analysis.Status.FAILED:
        run_and_store(session)
        analysis = getattr(session, "analysis", None)

    if analysis is None or analysis.status == analysis.Status.FAILED:
        raise ValueError(
            "The analysis did not complete, so a report cannot be generated. "
            "Run the analysis again when the compute service is available."
        )

    version = (existing.version + 1) if existing is not None else 1

    # Reserve the metadata row first so the report ID can appear in the PDF.
    report = Report.objects.create(
        session=session,
        patient=session.patient,
        version=version,
        generated_by=user if getattr(user, "is_authenticated", False) else None,
        analysis_snapshot={},
        pdf=b"",
    )

    payload = _payload(session, report, version)
    pdf_bytes = render_report(payload)

    report.analysis_snapshot = payload
    report.pdf = pdf_bytes
    report.file_size = len(pdf_bytes)
    report.checksum = hashlib.sha256(pdf_bytes).hexdigest()
    report.save(
        update_fields=["analysis_snapshot", "pdf", "file_size", "checksum"]
    )
    return report
