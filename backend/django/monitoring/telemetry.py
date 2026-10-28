"""Django <-> FastAPI compute and registry calls.

The telemetry service is the only owner of ECG samples and the DSP/inference
run. Django keeps the business record (patient, session, analysis snapshot,
report metadata) and calls FastAPI over HTTP for the computational work.

Two properties are deliberate:

* **Best effort on the request path.** Registering a session and analysing a
  recording must not fail because the compute service is briefly unavailable;
  the failure is recorded in ``SessionAnalysis.error`` and the operator can run
  the analysis again.
* **No new dependency.** ``urllib`` from the standard library is enough for a
  handful of JSON requests, so Django does not grow an HTTP client dependency
  for this.
"""

import json
import logging
import urllib.error
import urllib.request
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)

#: How long the self-issued token is valid. It is used immediately.
SYNC_TOKEN_LIFETIME = timedelta(minutes=5)


class TelemetryError(RuntimeError):
    """FastAPI could not answer a request Django needed."""


def build_session_payload(session) -> dict:
    """The ``known_sessions`` row FastAPI needs for this session.

    ``patient_id`` is the internal integer key of the permanent patient record.
    FastAPI treats it as an opaque value; it is not a foreign key across the two
    databases.
    """
    return {
        "session_id": str(session.id),
        "patient_id": session.patient_id,
        "device_id": str(session.device_id),
        "status": session.status,
    }


def issue_sync_token(now=None) -> str:
    """A short-lived admin access token, signed with the shared key.

    Shaped exactly like ``RoleTokenObtainPairSerializer`` output because FastAPI
    verifies both with the same code path. The user id is an identifier, not an
    account row.
    """
    now = now or timezone.now()
    payload = {
        "token_type": "access",
        "user_id": settings.TELEMETRY_SYNC_USER_ID,
        "role": "admin",
        "iat": now,
        "exp": now + SYNC_TOKEN_LIFETIME,
    }
    return jwt.encode(
        payload,
        settings.SIMPLE_JWT["SIGNING_KEY"],
        algorithm=settings.SIMPLE_JWT["ALGORITHM"],
    )


def _request_json(
    method: str,
    path: str,
    payload: dict | None = None,
    *,
    timeout: float | None = None,
) -> dict:
    url = f"{settings.TELEMETRY_BASE_URL.rstrip('/')}{path}"
    body = None
    headers = {"Authorization": f"Bearer {issue_sync_token()}"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"

    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(
            request, timeout=timeout or settings.TELEMETRY_SYNC_TIMEOUT_SECONDS
        ) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise TelemetryError(
            f"Telemetry service answered HTTP {exc.code} for {method} {path}: {detail}"
        ) from exc
    except (urllib.error.URLError, OSError, ValueError) as exc:
        raise TelemetryError(
            f"Could not reach the telemetry service at {url}: {exc}"
        ) from exc

    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise TelemetryError(
            f"Telemetry service returned a non-JSON body for {method} {path}."
        ) from exc


def sync_session(session) -> bool:
    """Push one session to FastAPI. Returns True on success, False otherwise.

    Never raises: a caller in the request path must not fail because the
    telemetry service is unavailable.
    """
    if not settings.TELEMETRY_SYNC_ENABLED:
        return False

    try:
        _request_json("POST", "/internal/sessions", build_session_payload(session))
    except TelemetryError as exc:
        logger.warning(
            "Could not register session %s with the telemetry service: %s. "
            "Ingestion for this session will answer 404 until a successful push.",
            session.id,
            exc,
        )
        return False

    logger.info("Registered session %s with the telemetry service.", session.id)
    return True


def run_analysis(session_id: str) -> dict:
    """Ask FastAPI to run DSP + inference on a stored recording.

    Raises ``TelemetryError`` when the service cannot be reached or refuses the
    analysis. The caller stores the failure rather than inventing a result.
    """
    # Sampling a whole recording is heavier than a heartbeat; give it time.
    return _request_json(
        "POST", f"/sessions/{session_id}/analysis", timeout=30.0
    )


def fetch_analysis(session_id: str) -> dict | None:
    """Return the latest stored analysis from FastAPI, or None if there is none."""
    try:
        return _request_json("GET", f"/sessions/{session_id}/analysis")
    except TelemetryError:
        return None


def fetch_session_ecg(session_id: str) -> dict:
    """All stored chunks for a session, used to draw the PDF waveform."""
    return _request_json(
        "GET", f"/internal/sessions/{session_id}/ecg", timeout=30.0
    )
