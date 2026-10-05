"""Django -> FastAPI session registry sync (one direction, best effort).

FastAPI must be able to reject data for a session it does not know **without
calling Django**, because a Django outage must not stop devices uploading. So
Django pushes each new and each stopped session to FastAPI's
`POST /internal/sessions`, authenticated with a short-lived admin token that
Django mints for itself.

Deliberate properties:

* **Best effort.** If FastAPI is down, session creation still succeeds and this
  logs a warning. A telemetry outage must not block clinical workflow.
* **Replayable.** The endpoint upserts, so re-sending any session at any time
  repairs a stale cache - which is exactly what a Phase 7 reconciliation job
  would do.
* **No new dependency.** `urllib` from the standard library is enough for one
  POST with a short timeout; adding an HTTP client to Django for this would be
  the wrong trade.
* **Synchronous.** Fine at demo scale (a few sessions a minute). Under real load
  this belongs on a queue with retries.
"""

import json
import logging
import urllib.error
import urllib.request
from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone

from accounts.models import DoctorAssignment

logger = logging.getLogger(__name__)

#: How long the self-issued admin token is valid. It is used immediately.
SYNC_TOKEN_LIFETIME = timedelta(minutes=5)


def build_session_payload(session) -> dict:
    """The `known_sessions` row FastAPI needs for this session."""
    doctor_ids = list(
        DoctorAssignment.objects.filter(patient=session.patient).values_list(
            "doctor__user_id", flat=True
        )
    )
    return {
        "session_id": str(session.id),
        "patient_id": session.patient.user_id,
        "device_id": str(session.device_id),
        "doctor_ids": doctor_ids,
        "status": session.status,
    }


def issue_sync_token(now=None) -> str:
    """A short-lived admin access token, signed with the shared key.

    Shaped exactly like `RoleTokenObtainPairSerializer` output because FastAPI
    verifies both with the same code path.
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


def sync_session(session) -> bool:
    """Push one session to FastAPI. Returns True on a 2xx, False otherwise.

    Never raises: a caller in the request path must not fail because the
    telemetry service is unavailable.
    """
    if not settings.TELEMETRY_SYNC_ENABLED:
        return False

    url = f"{settings.TELEMETRY_BASE_URL.rstrip('/')}/internal/sessions"
    payload = build_session_payload(session)
    body = json.dumps(payload).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {issue_sync_token()}",
        },
    )

    try:
        with urllib.request.urlopen(
            request, timeout=settings.TELEMETRY_SYNC_TIMEOUT_SECONDS
        ) as response:
            ok = 200 <= response.status < 300
    except (urllib.error.URLError, OSError, ValueError) as exc:
        logger.warning(
            "Could not register session %s with the telemetry service at %s: %s. "
            "Ingestion for this session will answer 404 until a successful push.",
            session.id,
            url,
            exc,
        )
        return False

    if not ok:  # pragma: no cover - urlopen raises for 4xx/5xx in practice
        logger.warning("Telemetry registry rejected session %s: %s", session.id, ok)
        return False

    logger.info("Registered session %s with the telemetry service.", session.id)
    return True
