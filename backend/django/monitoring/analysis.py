"""Analysis orchestration: FastAPI computes, Django stores the snapshot."""

import logging

from django.utils import timezone

from .models import Session, SessionAnalysis
from . import telemetry

logger = logging.getLogger(__name__)


def store_analysis(session: Session, payload: dict) -> SessionAnalysis:
    """Persist one FastAPI analysis response against the session."""
    signal = payload.get("signal") or {}
    ai = payload.get("ai") or {}

    remote_status = payload.get("status", "completed")
    quality = (signal.get("quality") or {})
    if remote_status == "unusable":
        status = SessionAnalysis.Status.UNUSABLE
    elif remote_status in {"failed", "unavailable"}:
        status = SessionAnalysis.Status.FAILED
    elif quality.get("usable") is False:
        status = SessionAnalysis.Status.UNUSABLE
    else:
        status = SessionAnalysis.Status.COMPLETED

    analysis, _ = SessionAnalysis.objects.update_or_create(
        session=session,
        defaults={
            "status": status,
            "result": payload,
            "model_version": (ai.get("model_version") or "")[:100],
            "analyzed_at": timezone.now(),
            "error": "",
        },
    )

    sample_rate = signal.get("sample_rate_hz")
    if sample_rate and session.sample_rate_hz != sample_rate:
        session.sample_rate_hz = sample_rate
        session.save(update_fields=["sample_rate_hz", "updated_at"])

    return analysis


def mark_failed(session: Session, message: str) -> SessionAnalysis:
    analysis, _ = SessionAnalysis.objects.update_or_create(
        session=session,
        defaults={
            "status": SessionAnalysis.Status.FAILED,
            "result": {},
            "model_version": "",
            "analyzed_at": timezone.now(),
            "error": message[:2000],
        },
    )
    return analysis


def run_and_store(session: Session) -> SessionAnalysis:
    """Run analysis through FastAPI and store it.

    An active session is refused: a moving recording is not a stable analysis
    target, and the operator should stop it first. The view translates this into
    a 400.
    """
    if session.status == Session.Status.ACTIVE:
        raise ValueError("Stop the recording before running the analysis.")

    try:
        payload = telemetry.run_analysis(str(session.id))
    except telemetry.TelemetryError as exc:
        logger.warning("Analysis failed for session %s: %s", session.id, exc)
        return mark_failed(session, str(exc))

    return store_analysis(session, payload)
